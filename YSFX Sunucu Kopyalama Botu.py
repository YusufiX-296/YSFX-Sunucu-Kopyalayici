#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YSFX Sunucu Kopyalama Botu
==============================================================================
KULLANIM
  1) Bu dosyayi (veya yanindaki "YSFX Sunucu Kopyalama Botu.bat") calistirin.
  2) Bot Tokenini yapistirin   (Discord Developer Portal > Bot > Token)
  3) Kaynak Sunucu ID = kopyalanacak DOLU sunucu  -> ASLA dokunulmaz
     Hedef  Sunucu ID = kendi BOŞ sunucunuz       -> icindekiler silinir,
                                kaynaktakinin aynisi yeniden kurulur
  4) Cikan davet linkiyle botu IKI sunucuya da davet edin.
  5) "Kopyalamayi Baslatmak Icin Enter Tusuna Basin" ile baslatin.
     Kopyalama ARKA PLANDA surerken komut satirindan yonetin:
        durum | duraklat | devam | iptal | log | davet | yardim | cikis

DISKTE OLUŞAN DOSYALAR (YSFXBot_Dosyalar icinde)
  ayarlar.json     girilen ID'ler + davet linki (token YAZILMAZ)
  bot_tokeni.txt   kayitli bot tokeni  (SADECE senin bilgisayarinda, PAYLASMA)
  davet_linki.txt  botu iki sunucuya davet etme linki
  bot_gunlugu.log  islem kaydi
==============================================================================
"""

from __future__ import annotations

import asyncio
import base64
import datetime as dt
import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------#
# Yollar ve sabitler
# ---------------------------------------------------------------------------#
BASLANGIC = os.path.dirname(os.path.abspath(__file__))
DOSYALAR = os.path.join(BASLANGIC, "YSFXBot_Dosyalar")
AYAR_YOL = os.path.join(DOSYALAR, "ayarlar.json")
TOKEN_YOL = os.path.join(DOSYALAR, "bot_tokeni.txt")
DAVET_YOL = os.path.join(DOSYALAR, "davet_linki.txt")
GUNLUK_YOL = os.path.join(DOSYALAR, "bot_gunlugu.log")

BANNER = (
    "██╗   ██╗███████╗ ████████╗██╗  ██╗ \n"
    "██║   ██║██╔════╝ ██╔═════╝██║  ██║ \n"
    "╚██╗ ██╔╝█████╗   █████╗   ╚██╗██╔╝ \n"
    " ╚████╔╝ ██╔══╝   ██╔══╝    ╚███╔╝  \n"
    "  ╚═══╝  ███████╗ ██║      ██║  ██║ \n"
    "         ╚══════╝ ██║      ╚═╝  ╚═╝ "
)
# ---------------------------------------------------------------------------#
# Durum (ana is parcacigi ile arka plandas async is parcacigi paylasir)
# ---------------------------------------------------------------------------#
DURUM = {
    "dongu": None,
    "istemci": None,
    "thread": None,
    "kapatildi": False,
    "ilk_hazir": False,
    "kopya_gorev": None,
    "adim": "-",
    "duraklatildi": False,
    "iptal": False,
    "bitti": False,
    "hata": None,
    "silinen_rol": 0,
    "silinen_kanal": 0,
    "yapilan_rol": 0,
    "yapilan_kategori": 0,
    "yapilan_kanal": 0,
    "yapilan_emoji": 0,
    "baslangic_zamani": None,
    "davet": "",
}

KAYNAK_ID = 0
HEDEF_ID = 0
KAYNAK_ADI = "?"
HEDEF_ADI = "?"

_GUNLUK_KILIT = threading.Lock()
_KONSOL_KILIT = threading.Lock()


class KopyalamaIptal(Exception):
    """Kullanici 'iptal' komutu verdiginde firlatilir."""


# ---------------------------------------------------------------------------#
# Bagimliliklar (discord.py / colorama yoksa pip ile kurulur)
# ---------------------------------------------------------------------------#
def _paket_kur(paketler, sebep):
    print(f"  [!] {sebep} -> pip ile kuruluyor: {' '.join(paketler)}")
    try:
        subprocess.call(
            [sys.executable, "-m", "pip", "install",
             "--disable-pip-version-check", "--quiet"] + paketler
        )
    except Exception as hata:
        print(f"  [HATA] pip calistirilamadi: {hata}")


def _bagimlilik_hazirla():
    os.makedirs(DOSYALAR, exist_ok=True)
    for mod, paket, ad in (("discord", ["discord.py"], "discord.py"),
                           ("colorama", ["colorama"], "colorama")):
        if importlib.util.find_spec(mod) is None:
            _paket_kur(paket, f"{ad} kurulu degil")
            importlib.invalidate_caches()
        if importlib.util.find_spec(mod) is None:
            sys.exit(f"  [HATA] {ad} kurulamadi. Elle kurun: "
                     f"{sys.executable} -m pip install {' '.join(paket)}")


_bagimlilik_hazirla()

import discord  # noqa: E402
from colorama import Fore, Style, init as colorama_init  # noqa: E402

colorama_init()

for _akim in (sys.stdout, sys.stderr):
    try:
        _akim.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
try:
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

try:
    if int(discord.__version__.split(".")[0]) < 2:
        _paket_kur(["--upgrade", "discord.py"], "discord.py 1.x bulundu")
        sys.exit("  [BILGI] Guncelleme yapildi; dosyayi tekrar calistirin.")
except ValueError:
    pass


# ---------------------------------------------------------------------------#
# Yardimcilar
# ---------------------------------------------------------------------------#
def kayit(seviye, mesaj):
    """Ekrana + gunluk dosyasina yazar (iki parcaciktan guvenli)."""
    damga = dt.datetime.now().strftime("%H:%M:%S")
    satir = f"[{damga}] [{seviye}] {mesaj}"
    with _GUNLUK_KILIT:
        with _KONSOL_KILIT:
            print(f"  {satir}")
        try:
            with open(GUNLUK_YOL, "a", encoding="utf-8") as f:
                f.write(satir + "\n")
        except Exception:
            pass


def adim_ayla(metin):
    DURUM["adim"] = metin
    kayit("ADIM", metin)


def sor(etiket):
    return input(f"  {Fore.GREEN}[{Fore.RED}>{Style.RESET_ALL}"
                 f"{Fore.GREEN}]{Style.RESET_ALL} {etiket} ").strip()


def token_kaydet(token):
    try:
        with open(TOKEN_YOL, "w", encoding="utf-8") as f:
            f.write(token.strip() + "\n")
        return True
    except Exception as hata:
        print(f"  [UYARI] Token diske yazilamadi: {hata}")
        return False


def _kayitli_token():
    if not os.path.exists(TOKEN_YOL):
        return None
    try:
        with open(TOKEN_YOL, encoding="utf-8") as f:
            aday = f.read().strip()
        if aday and len(aday.split(".")) == 3 and all(aday.split(".")):
            return aday
    except Exception:
        return None
    return None


def token_al():
    kayitli = _kayitli_token()
    if kayitli:
        gizli = "***" + kayitli[-6:]
        cevap = sor(f"Kayitli token bulundu ({gizli}) -> Enter = kullan, "
                    f"'y' = yeni token :")
        if cevap.lower() in ("y", "yeni", "yeni token"):
            print("  [i] Yeni token istenecek.")
        else:
            print(f"  [i] Kayitli token kullaniliyor ({gizli}).")
            return kayitli
    while True:
        token = sor("Bot Tokeni :")
        if not token:
            sys.exit("  [HATA] Token verilmedi.")
        parca = token.split(".")
        if len(parca) == 3 and all(parca):
            token_kaydet(token)
            return token
        print("  [HATA] Token 'ilk.son.uc' biciminde olmali "
              "(Discord Developer Portal > Bot > Token).")


def id_al(etiket, aciklama):
    while True:
        deger = sor(f"{etiket} ({aciklama}) :")
        if not deger:
            sys.exit("  [HATA] ID verilmedi.")
        temiz = deger.strip().strip("\"'<>@& ").replace(" ", "")
        if temiz.isdigit() and 15 <= len(temiz) <= 22:
            return int(temiz)
        print("  [HATA] Gecerli sunucu ID rakamlardan olusur "
              "(orn. 123456789012345678).")


# ---------------------------------------------------------------------------#
# Discord on-kontrolu (token + bot iki sunucuda mi? -> silmeden once dogrular)
# ---------------------------------------------------------------------------#
def api_cagir(token, yol):
    istek = urllib.request.Request(
        "https://discord.com/api/v10" + yol,
        method="GET",
        headers={"Authorization": f"Bot {token}",
                 "User-Agent": "YSFXServerCloner/1.0"},
    )
    with urllib.request.urlopen(istek, timeout=20) as yanit:
        govde = yanit.read()
    return json.loads(govde) if govde else {}


def hizli_kontrol(token, kaynak, hedef):
    """-> (durum, mesaj, bilgi); durum: ok | token | sunucu | ag"""
    try:
        ben = api_cagir(token, "/users/@me")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return ("token",
                    "Token reddedildi (HTTP %s). Developer Portal'dan "
                    "yeni token alin." % e.code, {})
        return "ag", f"Discord API hatasi: HTTP {e.code}", {}
    except Exception as e:
        return "ag", f"Internet/Discord baglanti hatasi: {e}", {}

    if not ben.get("bot"):
        return ("token",
                "Bu bir BOT tokeni degil (bot: false). Yanlis deger "
                "yapistirilmis olabilir.", {})

    bilgi = {"bot_adi": ben.get("username", "?"), "kaynak": None, "hedef": None}
    for etiket, gid in (("kaynak", kaynak), ("hedef", hedef)):
        try:
            guild = api_cagir(token, f"/guilds/{gid}")
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return ("sunucu",
                        f"Bot '{etiket.upper()}' sunucusunda degil veya ID "
                        f"hatali (HTTP {e.code}).", bilgi)
            return "ag", f"{etiket} sorgusu HTTP {e.code}", bilgi
        except Exception as e:
            return "ag", str(e), bilgi

        sayim = {"ad": guild.get("name", "?"),
                 "rol": None, "kanal": None,
                 "emoji": len(guild.get("emojis") or [])}
        for alt, anahtar in ((f"/guilds/{gid}/roles", "rol"),
                             (f"/guilds/{gid}/channels", "kanal")):
            try:
                sayim[anahtar] = len(api_cagir(token, alt))
            except Exception:
                sayim[anahtar] = None
        bilgi[etiket] = sayim
    return "ok", "", bilgi


# ---------------------------------------------------------------------------#
# Davet linki
# ---------------------------------------------------------------------------#
def token_client_id(token):
    try:
        ilk = token.split(".")[0]
        veri = base64.urlsafe_b64decode(ilk + "=" * (-len(ilk) % 4))
        sayi = veri.decode("ascii", "ignore").strip().strip("\x00")
        return sayi if sayi.isdigit() else None
    except Exception:
        return None


def izin_sayisi():
    izinler = discord.Permissions.none()
    izinler.manage_roles = True          # rol olustur/sil
    izinler.manage_channels = True       # kanal olustur/sil
    izinler.manage_guild = True          # sunucu adi + ikon
    izinler.manage_emojis_and_stickers = True
    izinler.view_channel = True
    return int(izinler.value)


def davet_yap(client_id):
    return (f"https://discord.com/oauth2/authorize?client_id={client_id}"
            f"&permissions={izin_sayisi()}&scope=bot")


def dosyalara_yaz(client_id, davet, bilgi):
    kaynak_b = bilgi.get("kaynak") or {}
    hedef_b = bilgi.get("hedef") or {}
    veri = {
        "olusturma": dt.datetime.now().isoformat(timespec="seconds"),
        "bot_adi": bilgi.get("bot_adi"),
        "bot_client_id": client_id,
        "kaynak_sunucu_id": str(KAYNAK_ID),
        "kaynak_sunucu_adi": kaynak_b.get("ad", KAYNAK_ADI),
        "hedef_sunucu_id": str(HEDEF_ID),
        "hedef_sunucu_adi": hedef_b.get("ad", HEDEF_ADI),
        "davet_linki": davet,
        "kopyalama_yonu": "Kaynak (dolu, DOKUNULMAZ) -> Hedef (bos sunucunuz)",
        "izinler": izin_sayisi(),
    }
    try:
        with open(AYAR_YOL, "w", encoding="utf-8") as f:
            json.dump(veri, f, ensure_ascii=False, indent=2)
    except Exception as hata:
        kayit("UYARI", f"ayarlar.json yazilamadi: {hata}")
    try:
        with open(DAVET_YOL, "w", encoding="utf-8") as f:
            f.write(
                "YSFX Sunucu Kopyalama Botu - DAVET LINKI\n"
                "==========================================\n"
                f"{davet}\n\n"
                "1) Bu linkle botu KAYNAK (dolu) sunucuya davet edin.\n"
                "2) Ayni linkle botu HEDEF (bos) sunucuya davet edin.\n"
                "Gerekli yetkiler: Roller, Kanallar, Sunucu, Emojileri Yonet, \n"
                "Goruntuleme.\n"
            )
    except Exception as hata:
        kayit("UYARI", f"davet_linki.txt yazilamadi: {hata}")


# ---------------------------------------------------------------------------#
# Kopyalama
# ---------------------------------------------------------------------------#
async def akis():
    """Duraklat / iptal kontrolu - her adimdan once cagrilir."""
    while DURUM["duraklatildi"] and not DURUM["iptal"]:
        await asyncio.sleep(0.3)
    if DURUM["iptal"]:
        raise KopyalamaIptal()


def ow_yap(hedef, overwrites, eski_yeni):
    """Kaynak kanal izinlerini hedefteki rollere esler (roller id ile)."""
    sonuc = {}
    for hedef_obj, izin in overwrites.items():
        if not isinstance(hedef_obj, discord.Role):
            continue                      # uyeler kopyalanmaz
        if hedef_obj.is_default():
            yeni = hedef.default_role
        else:
            cift = eski_yeni.get(hedef_obj.id)
            yeni = cift[1] if cift else discord.utils.get(
                hedef.roles, name=hedef_obj.name)
        if yeni is None:
            continue
        sonuc[yeni] = izin
    return sonuc


async def kanal_basit(hedef, ch, kategori, ow):
    """Ilk deneme basarisiz olursa sade ozellikle tekrar dener."""
    tip = ch.type
    if tip in (discord.ChannelType.voice, discord.ChannelType.stage_voice):
        return await hedef.create_voice_channel(
            name=ch.name, category=kategori, overwrites=ow)
    if tip is discord.ChannelType.forum:
        try:
            return await hedef.create_forum(
                name=ch.name, category=kategori, overwrites=ow)
        except Exception:
            pass
    return await hedef.create_text_channel(
        name=ch.name, category=kategori, overwrites=ow)


async def kanal_olustur(hedef, ch, kategori, ow):
    tip = ch.type
    konum = getattr(ch, "position", None)

    if tip is discord.ChannelType.forum:
        ek = {}
        if getattr(ch, "topic", None):
            ek["topic"] = ch.topic
        if getattr(ch, "slowmode_delay", None):
            ek["slowmode_delay"] = ch.slowmode_delay
        return await hedef.create_forum(
            name=ch.name, category=kategori, overwrites=ow,
            position=konum, **ek)

    if tip in (discord.ChannelType.text, discord.ChannelType.news):
        ek = {}
        if getattr(ch, "topic", None):
            ek["topic"] = ch.topic
        if getattr(ch, "slowmode_delay", None):
            ek["slowmode_delay"] = ch.slowmode_delay
        if getattr(ch, "nsfw", False):
            ek["nsfw"] = True
        return await hedef.create_text_channel(
            name=ch.name, category=kategori, overwrites=ow,
            position=konum, news=(tip is discord.ChannelType.news), **ek)

    if tip is discord.ChannelType.stage_voice:
        return await hedef.create_stage_channel(
            name=ch.name, category=kategori, overwrites=ow, position=konum)

    if tip is discord.ChannelType.voice:
        try:
            return await hedef.create_voice_channel(
                name=ch.name, category=kategori, overwrites=ow,
                position=konum, bitrate=ch.bitrate,
                user_limit=ch.user_limit)
        except discord.HTTPException:
            # hedef sunucunun bitratesi/kotasi asilirsa sade denemesi
            return await hedef.create_voice_channel(
                name=ch.name, category=kategori, overwrites=ow,
                position=konum)

    # bilinmeyen/beni desteklemeyen tip -> metin kanali
    return await hedef.create_text_channel(
        name=ch.name, category=kategori, overwrites=ow)


async def kopyala_sunucu(kaynak, hedef):
    eski_yeni = {}          # kaynak rol id -> (kaynak rol, yeni rol)

    # 1) sunucu adi + simge
    adim_ayla("1/7 Sunucu adi ve simgesi kopyalanıyor")
    ikon = None
    if kaynak.icon is not None:
        try:
            ikon = await kaynak.icon.read()
        except Exception as hata:
            kayit("UYARI", f"Sunucu simgesi okunamadi: {hata}")
    try:
        if ikon:
            await hedef.edit(name=kaynak.name, icon=ikon)
        else:
            await hedef.edit(name=kaynak.name)
        kayit("OK", f"Sunucu adi/simgesi guncellendi -> {kaynak.name}")
    except Exception as hata:
        kayit("HATA", f"Sunucu adi/simgesi kopyalanamadi: {hata}")

    # 2) hedefteki roller sil (kaynak sunucuya dokunulmaz)
    adim_ayla("2/7 Hedef sunucudaki roller siliniyor")
    for rol in list(hedef.roles):
        if rol.is_default():
            continue
        if rol.managed:
            kayit("ATLA", f"Rol (yonetilen, silinemez): {rol.name}")
            continue
        await akis()
        try:
            await rol.delete()
            DURUM["silinen_rol"] += 1
            kayit("SIL", f"Rol: {rol.name}")
        except discord.NotFound:
            pass
        except discord.Forbidden:
            kayit("HATA", f"Rol silinemedi (yetki eksik): {rol.name}")
        except discord.HTTPException as hata:
            kayit("HATA", f"Rol silinemedi: {rol.name} ({hata})")

    # 3) hedefteki kanallar sil (once alt kanallar, sonra kategoriler)
    adim_ayla("3/7 Hedef sunucudaki kanallar siliniyor")
    hedef_kanallar = list(hedef.channels)
    sirali_sil = ([c for c in hedef_kanallar
                   if c.type is not discord.ChannelType.category] +
                  [c for c in hedef_kanallar
                   if c.type is discord.ChannelType.category])
    for ch in sirali_sil:
        await akis()
        try:
            await ch.delete()
            DURUM["silinen_kanal"] += 1
            kayit("SIL", f"Kanal: {ch.name}")
        except discord.NotFound:
            pass
        except discord.Forbidden:
            kayit("HATA", f"Kanal silinemedi (yetki eksik): {ch.name}")
        except discord.HTTPException as hata:
            kayit("HATA", f"Kanal silinemedi: {ch.name} ({hata})")

    # 4) roller olustur (en yuksekten asagiya -> hiyerarsi korunur)
    adim_ayla("4/7 Roller olusturuluyor")
    kaynak_rolleri = [r for r in kaynak.roles if not r.is_default()]
    kaynak_rolleri.sort(key=lambda r: r.position, reverse=True)
    for rol in kaynak_rolleri:
        await akis()
        try:
            yeni = await hedef.create_role(
                name=rol.name, permissions=rol.permissions,
                colour=rol.colour, hoist=rol.hoist,
                mentionable=rol.mentionable)
            eski_yeni[rol.id] = (rol, yeni)
            DURUM["yapilan_rol"] += 1
            kayit("YAP", f"Rol: {rol.name}")
        except discord.HTTPException as hata:
            kayit("HATA", f"Rol olusturulamadi: {rol.name} ({hata})")
    if eski_yeni:
        try:
            konumlar = {yeni: eski.position
                        for eski, yeni in eski_yeni.values()}
            await hedef.edit_role_positions(positions=konumlar)
            kayit("OK", "Rol siralamasi (hiyerarsi) kopyalandi")
        except Exception as hata:
            kayit("UYARI",
                  f"Rol siralamasi kopyalanamadi (elle yapilabilir): {hata}")

    # 5) kategoriler
    adim_ayla("5/7 Kategoriler olusturuluyor")
    kategoriler = sorted(
        [c for c in kaynak.channels
         if c.type is discord.ChannelType.category],
        key=lambda c: c.position)
    kategori_yeni = {}
    for cat in kategoriler:
        await akis()
        ow = ow_yap(hedef, cat.overwrites, eski_yeni)
        try:
            yeni = await hedef.create_category(
                name=cat.name, overwrites=ow, position=cat.position)
            kategori_yeni[cat.id] = yeni
            DURUM["yapilan_kategori"] += 1
            kayit("YAP", f"Kategori: {cat.name}")
        except discord.HTTPException as hata:
            kayit("HATA", f"Kategori olusturulamadi: {cat.name} ({hata})")

    # 6) metin / ses / sahne / forum kanallari
    adim_ayla("6/7 Kanallar olusturuluyor")
    sira = {cat.id: i for i, cat in enumerate(kategoriler)}

    def sira_anahtari(ch):
        ust = ch.category.id if ch.category else -1
        return (sira.get(ust, -1), getattr(ch, "position", 0))

    dagitici = [c for c in kaynak.channels
                if c.type is not discord.ChannelType.category]
    for ch in sorted(dagitici, key=sira_anahtari):
        await akis()
        ow = ow_yap(hedef, ch.overwrites, eski_yeni)
        kategori = None
        if ch.category is not None:
            kategori = kategori_yeni.get(ch.category.id)
        try:
            yeni = await kanal_olustur(hedef, ch, kategori, ow)
        except (discord.Forbidden, discord.HTTPException, TypeError,
                ValueError) as hata:
            kayit("UYARI",
                  f"'{ch.name}' tam ozellikle olusturulamadi ({hata}); "
                  f"basit mod deneniyor")
            try:
                yeni = await kanal_basit(hedef, ch, kategori, ow)
            except Exception as hata2:
                kayit("HATA", f"Kanal olusturulamadi: {ch.name} ({hata2})")
                yeni = None
        if yeni is not None:
            DURUM["yapilan_kanal"] += 1
            kayit("YAP", f"Kanal: {ch.name}")

    # 7) emojiler
    adim_ayla("7/7 Emojiler kopyalanıyor")
    for emoji in list(kaynak.emojis):
        await akis()
        try:
            resim = await emoji.url.read()
            await hedef.create_custom_emoji(name=emoji.name, image=resim)
            DURUM["yapilan_emoji"] += 1
            kayit("YAP", f"Emoji: {emoji.name}")
        except discord.Forbidden:
            kayit("UYARI",
                  f"Emoji kopyalanamadi (yetki/doluluk): {emoji.name}")
        except Exception as hata:
            kayit("HATA", f"Emoji kopyalanamadi: {emoji.name} ({hata})")


async def kopyayi_baslat(istemci, kaynak_id, hedef_id):
    kaynak = istemci.get_guild(kaynak_id)
    hedef = istemci.get_guild(hedef_id)
    if kaynak is None or hedef is None:
        DURUM["adim"] = "hata"
        kayit("HATA", "Sunucular bulunamadi (bot davet edilmemis olabilir).")
        DURUM["bitti"] = True
        return

    DURUM["baslangic_zamani"] = time.time()
    kayit("BILGI", f"KOPYALAMA BASLADI: '{kaynak.name}' -> '{hedef.name}'")
    try:
        await kopyala_sunucu(kaynak, hedef)
    except KopyalamaIptal:
        DURUM["adim"] = "iptal"
        DURUM["bitti"] = True
        kayit("UYARI", "Kopyalama IPTAL edildi; hedef sunucu yarim "
                       "kalmis olabilir.")
        return
    except Exception:
        DURUM["adim"] = "hata"
        DURUM["bitti"] = True
        kayit("HATA", "Beklenmeyen hata:\n" + traceback.format_exc())
        return

    DURUM["adim"] = "tamam"
    DURUM["bitti"] = True
    sure = int(time.time() - DURUM["baslangic_zamani"])
    kayit("OK", f"KOPYALAMA TAMAMLANDI ({sure} sn)")
    with _KONSOL_KILIT:
        print(f"\n  {Fore.GREEN}Islem bitti. Ozet icin 'durum', "
              f"kapatmak icin 'cikis' yazin.{Style.RESET_ALL}\n")


async def _bas_kontrol(istemci):
    """Her iki sunucu da hazirsa kopyalamayi bir kez baslatir."""
    if DURUM["kopya_gorev"] is not None or DURUM["bitti"] or DURUM["iptal"]:
        return
    kaynak = istemci.get_guild(KAYNAK_ID)
    hedef = istemci.get_guild(HEDEF_ID)
    if kaynak is None or hedef is None:
        return
    DURUM["kopya_gorev"] = asyncio.create_task(
        kopyayi_baslat(istemci, KAYNAK_ID, HEDEF_ID))


def istemci_kur():
    istemci = discord.Client(intents=discord.Intents.default())

    @istemci.event
    async def on_ready():
        if DURUM["ilk_hazir"]:
            return
        DURUM["ilk_hazir"] = True
        kayit("OK", f"Bot baglandi: {istemci.user} (ID {istemci.user.id})")
        eksik = []
        if istemci.get_guild(KAYNAK_ID) is None:
            eksik.append(f"KAYNAK ({KAYNAK_ID})")
        if istemci.get_guild(HEDEF_ID) is None:
            eksik.append(f"HEDEF ({HEDEF_ID})")
        if eksik:
            kayit("UYARI", "Bot su sunucularda degil: " + ", ".join(eksik))
            if DURUM["davet"]:
                kayit("UYARI", "Once bu linkle davet edin: " + DURUM["davet"])
            kayit("UYARI", "Davet ettikten sonra bot otomatik baslar "
                           "(sunucular geldiginde).")
        else:
            await _bas_kontrol(istemci)

    @istemci.event
    async def on_guild_join(guild):
        # ilk hazirliktan sonra gelirse (davet edildiyse) otomatik baslar
        if DURUM["ilk_hazir"]:
            kayit("BILGI", f"Sunucuya katildi: {guild.name}")
            await _bas_kontrol(istemci)

    return istemci


def arka_plan_baslat(token):
    """Discord baglantisini AYRI thread'te calistirir (konsol serbest kalir)."""
    def _calistir():
        dongu = asyncio.new_event_loop()
        asyncio.set_event_loop(dongu)
        DURUM["dongu"] = dongu
        istemci = istemci_kur()
        DURUM["istemci"] = istemci
        try:
            dongu.run_until_complete(istemci.start(token))
        except discord.LoginFailure:
            DURUM["hata"] = "token"
            kayit("HATA", "Token reddedildi (401). Yeni token alip "
                          "tekrar deneyin.")
        except Exception:
            if not DURUM["iptal"]:
                DURUM["hata"] = DURUM["hata"] or "bilinmiyor"
                kayit("HATA", "Arka plan hatasi:\n" + traceback.format_exc())
        finally:
            try:
                if not istemci.is_closed():
                    dongu.run_until_complete(istemci.close())
            except Exception:
                pass
            try:
                dongu.close()
            except Exception:
                pass
            DURUM["kapatildi"] = True

    thread = threading.Thread(target=_calistir, name="YSFX-arkaplan",
                              daemon=True)
    DURUM["thread"] = thread
    thread.start()
    kayit("BILGI", "Arka plan baslatildi; kopyalama baglanti kurulunca "
                   "otomatik olarak baslar.")


# ---------------------------------------------------------------------------#
# Konsol komutlari
# ---------------------------------------------------------------------------#
def yardim_yaz():
    print(f"  {Fore.CYAN}Komutlar:{Style.RESET_ALL} "
          "durum | duraklat | devam | iptal | log [n] | davet | yardim | cikis")


def durum_yaz():
    print(f"  Adim        : {DURUM['adim']}")
    duraklat = "Evet" if DURUM["duraklatildi"] else "Hayir"
    bitti = "Evet" if DURUM["bitti"] else "Hayir"
    print(f"  Duraklatildi: {duraklat}   Bitti: {bitti}")
    print(f"  Silinen     : {DURUM['silinen_rol']} rol, "
          f"{DURUM['silinen_kanal']} kanal")
    print(f"  Yapilan     : {DURUM['yapilan_rol']} rol, "
          f"{DURUM['yapilan_kategori']} kategori, "
          f"{DURUM['yapilan_kanal']} kanal, {DURUM['yapilan_emoji']} emoji")
    if DURUM["baslangic_zamani"]:
        gecen = int(time.time() - DURUM["baslangic_zamani"])
        print(f"  Gecen sure  : {gecen} sn")
    if DURUM["hata"]:
        print(f"  HATA        : {DURUM['hata']}")


def log_yaz(adet):
    try:
        with open(GUNLUK_YOL, encoding="utf-8") as f:
            satirlar = f.readlines()
    except Exception:
        print("  [i] Henuz gunluk yok.")
        return
    print(f"  --- gunlugun son {min(adet, len(satirlar))} satiri ---")
    for satir in satirlar[-adet:]:
        print("  " + satir.rstrip())


def komut_isle(metin):
    parca = metin.strip().split()
    if not parca:
        return True
    komut = parca[0].lower()

    if komut in ("durum", "status"):
        durum_yaz()
    elif komut == "duraklat":
        if DURUM["bitti"]:
            print("  [i] Kopyalama zaten bitti.")
        else:
            DURUM["duraklatildi"] = True
            print("  [i] DURAKLATILDI. 'devam' ile surer.")
    elif komut == "devam":
        DURUM["duraklatildi"] = False
        print("  [i] Devam ediliyor.")
    elif komut == "iptal":
        DURUM["iptal"] = True
        DURUM["duraklatildi"] = False
        print("  [!] IPTAL istendi; arka plandaki islem duracak.")
    elif komut == "log":
        adet = 15
        if len(parca) > 1 and parca[1].isdigit():
            adet = int(parca[1])
        log_yaz(adet)
    elif komut == "davet":
        print("  " + (DURUM["davet"] or "(davet linki yok)"))
    elif komut in ("yardim", "help", "?"):
        yardim_yaz()
    elif komut in ("cikis", "quit", "exit", "q"):
        print("  [i] Kapatiliyor...")
        DURUM["iptal"] = True
        return False
    else:
        print(f"  [?] Bilinmeyen komut: {komut} - 'yardim' yazin.")
    return True


def komut_dongusu():
    print(f"\n  {Fore.CYAN}--- KOMUT SATIRI (yazip Enter) ---{Style.RESET_ALL}")
    yardim_yaz()
    while True:
        if DURUM["kapatildi"]:
            print("  [i] Discord baglantisi kapandi.")
            break
        try:
            satir = input(f"  {Fore.CYAN}YSFX>{Style.RESET_ALL} ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not satir.strip():
            continue
        if not komut_isle(satir):
            break


def kapanis():
    DURUM["iptal"] = True
    dongu = DURUM["dongu"]
    istemci = DURUM["istemci"]
    thread = DURUM["thread"]
    if istemci is not None and dongu is not None and not DURUM["kapatildi"]:
        try:
            asyncio.run_coroutine_threadsafe(
                istemci.close(), dongu).result(timeout=15)
        except Exception:
            pass
    if thread is not None and thread.is_alive():
        thread.join(timeout=15)

    print(f"\n  {Fore.MAGENTA}SON OZET{Style.RESET_ALL}")
    print(f"  Silinen : {DURUM['silinen_rol']} rol, "
          f"{DURUM['silinen_kanal']} kanal")
    print(f"  Yapilan : {DURUM['yapilan_rol']} rol, "
          f"{DURUM['yapilan_kategori']} kategori, "
          f"{DURUM['yapilan_kanal']} kanal, {DURUM['yapilan_emoji']} emoji")
    kayit("BILGI", "Program kapatildi.")


# ---------------------------------------------------------------------------#
# Ana akis
# ---------------------------------------------------------------------------#
def baslik_yaz():
    print()
    print(f"{Fore.BLUE}{BANNER}{Style.RESET_ALL}")
    print(f"  {Fore.MAGENTA}YSFX Sunucu Kopyalama Botu  -  "
          f"developed for YSFX{Style.RESET_ALL}")
    print(f"  {Fore.YELLOW}Botu once Discord Developer Portal'dan aldigiz "
          f"token ile calistirin.{Style.RESET_ALL}\n")


def main():
    global KAYNAK_ID, HEDEF_ID, KAYNAK_ADI, HEDEF_ADI
    os.makedirs(DOSYALAR, exist_ok=True)
    baslik_yaz()

    bilgi = {}
    while True:
        token = token_al()
        KAYNAK_ID = id_al("Kaynak Sunucu ID :",
                          "kopyalanacak DOLU sunucu, dokunulmaz")
        HEDEF_ID = id_al("Hedef  Sunucu ID :",
                         "kendi BOŞ sunucunuz, icindekiler yeniden kurulur")
        if KAYNAK_ID == HEDEF_ID:
            print("  [HATA] Kaynak ve hedef AYNI sunucu olamaz!")
            continue

        if os.environ.get("YSFX_KONTROL_ATLA") == "1":
            kayit("UYARI", "YSFX_KONTROL_ATLA=1 -> on kontrol atlandi "
                           "(test modu)")
            break

        durum, mesaj, bilgi = hizli_kontrol(token, KAYNAK_ID, HEDEF_ID)
        if durum == "ok":
            break
        print(f"  [HATA] {mesaj}")
        if durum == "token":
            try:
                os.remove(TOKEN_YOL)
            except OSError:
                pass
            print("  Kayitli token silindi; yenisi istenecek.")
            continue
        if durum == "sunucu":
            cevap = sor("Botu davet edip tekrar denemek ister misiniz? (e/h) :")
            if cevap.lower() in ("e", "evet", "y"):
                continue
        sys.exit("  [HATA] Kontrol asilamadi; kapatiliyor.")

    kaynak_b = bilgi.get("kaynak") or {}
    hedef_b = bilgi.get("hedef") or {}
    KAYNAK_ADI = kaynak_b.get("ad", KAYNAK_ADI)
    HEDEF_ADI = hedef_b.get("ad", HEDEF_ADI)

    # --- davet linki ---
    client_id = token_client_id(token)
    if not client_id:
        client_id = sor("Client ID bulunamadi - Developer Portal > "
                        "General Information > Client ID :")
        while not client_id.isdigit():
            client_id = sor("Gecerli Client ID (sadece rakam) :")
    davet = davet_yap(client_id)
    DURUM["davet"] = davet
    dosyalara_yaz(client_id, davet, bilgi)

    print()
    print(f"  {Fore.YELLOW}Bot Davet Linki :{Style.RESET_ALL}")
    print(f"  {Fore.CYAN}{davet}{Style.RESET_ALL}")
    print(f"  {Fore.YELLOW}  (link dosyaya yazildi: "
          f"{os.path.relpath(DAVET_YOL, BASLANGIC)}){Style.RESET_ALL}")
    print()
    print(f"  {Fore.GREEN}[i] KAYNAK :{Style.RESET_ALL} {KAYNAK_ADI} "
          f"({KAYNAK_ID}) - bu sunucuya HIC dokunulmayacak.")
    rol_b = hedef_b.get("rol")
    kanal_b = hedef_b.get("kanal")
    if rol_b is not None and kanal_b is not None:
        print(f"  {Fore.RED}[i] HEDEF  :{Style.RESET_ALL} {HEDEF_ADI} "
              f"({HEDEF_ID}) - icindeki {rol_b} rol ve {kanal_b} kanal "
              f"silinip yeniden kurulacak.")
    else:
        print(f"  {Fore.RED}[i] HEDEF  :{Style.RESET_ALL} {HEDEF_ADI} "
              f"({HEDEF_ID}) - icindekiler silinip kopyalanacak.")
    print()
    print(f"  {Fore.YELLOW}Botu iki sunucuya da davet ettiginizden emin "
          f"olun.{Style.RESET_ALL}")

    try:
        input(f"\n  {Fore.GREEN}Kopyalamayi Baslatmak Icin Enter Tusuna "
              f"Basin {Style.RESET_ALL}")
    except (EOFError, KeyboardInterrupt):
        sys.exit("\n  [HATA] Girdi kapandi; kapatiliyor.")

    arka_plan_baslat(token)
    komut_dongusu()
    kapanis()
    input(f"\n  Kapatmak icin Enter'a basin ... ")


if __name__ == "__main__":
    cikis_kodu = 0
    try:
        main()
    except SystemExit as olay:
        if isinstance(olay.code, str):
            print(olay.code)
            cikis_kodu = 1
        else:
            cikis_kodu = int(olay.code or 0)
    except KeyboardInterrupt:
        print("\n  [i] Durduruldu (Ctrl+C).")
        cikis_kodu = 1
    except EOFError:
        print("\n  [i] Girdi kapatildi.")
        cikis_kodu = 1
    except Exception:
        print("\n  [HATA] Beklenmeyen hata:\n" + traceback.format_exc())
        cikis_kodu = 1
    sys.exit(cikis_kodu)
