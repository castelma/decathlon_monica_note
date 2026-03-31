import json
import os
from datetime import date, timedelta, datetime

# ── Costanti ────────────────────────────────────────────────────────────────

MENSILE_PATH = "../decathlon_monica_calendario/data/events_mensile.json"
SETTIMANALE_PATH = "../decathlon_monica_calendario/data/events_settimanale.json"
NOTA_PATH = "nota.txt"
LAST_UPDATE_PATH = "last_update.txt"

GIORNI_ITA = ["Lunedì","Martedì","Mercoledì","Giovedì","Venerdì","Sabato","Domenica"]
MESI_ITA = ["","Gennaio","Febbraio","Marzo","Aprile","Maggio","Giugno",
            "Luglio","Agosto","Settembre","Ottobre","Novembre","Dicembre"]

# ── Festivi aziendali ────────────────────────────────────────────────────────

def calcola_pasqua(anno):
    """Algoritmo di Butcher per il calcolo della Pasqua."""
    a = anno % 19
    b = anno // 100
    c = anno % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mese = (h + l - 7 * m + 114) // 31
    giorno = ((h + l - 7 * m + 114) % 31) + 1
    return date(anno, mese, giorno)

def get_festivi(anno):
    pasqua = calcola_pasqua(anno)
    pasquetta = pasqua + timedelta(days=1)
    festivi = {
        date(anno, 1, 1),   # Capodanno
        pasqua,             # Pasqua
        pasquetta,          # Pasquetta
        date(anno, 8, 15),  # Ferragosto
        date(anno, 12, 25), # Natale
        date(anno, 12, 26), # Santo Stefano
    }
    return festivi

# ── Helpers ──────────────────────────────────────────────────────────────────

def is_weekend(d):
    return d.weekday() >= 5  # 5=Sabato, 6=Domenica

def is_festivo(d, festivi_cache):
    anno = d.year
    if anno not in festivi_cache:
        festivi_cache[anno] = get_festivi(anno)
    return d in festivi_cache[anno]

def is_giorno_ignorato(d, festivi_cache):
    """Weekend o festivo aziendale → non rompe la catena."""
    return is_weekend(d) or is_festivo(d, festivi_cache)

def format_data(d):
    return f"{GIORNI_ITA[d.weekday()]} {d.day} {MESI_ITA[d.month]}"

def format_data_corta(d):
    return f"{GIORNI_ITA[d.weekday()]} {d.day}"

# ── Parsing eventi ────────────────────────────────────────────────────────────

def is_ferie(title):
    return "FERIE" in title.upper()

def is_indispo(title):
    return "INDISPO" in title.upper()

def is_rilevante(title):
    return is_ferie(title) or is_indispo(title)

def has_punto_interrogativo(title):
    return "?" in title

def parse_eventi(data):
    """
    Restituisce lista di dict con:
      - date_start: date
      - date_end: date (inclusa)
      - title: str
      - is_ferie: bool
      - is_indispo: bool
      - in_attesa: bool
    """
    eventi = []
    for ev in data:
        title = ev.get("title", "")
        if not is_rilevante(title):
            continue
        try:
            d_start = date.fromisoformat(ev["date"])
        except Exception:
            continue
        end_date_raw = ev.get("end_date")
        if end_date_raw:
            try:
                d_end = date.fromisoformat(end_date_raw)
            except Exception:
                d_end = d_start
        else:
            d_end = d_start

        eventi.append({
            "date_start": d_start,
            "date_end": d_end,
            "title": title,
            "is_ferie": is_ferie(title),
            "is_indispo": is_indispo(title),
            "in_attesa": has_punto_interrogativo(title),
        })
    return eventi

# ── Deduplicazione ────────────────────────────────────────────────────────────

def deduplicа_eventi(eventi):
    """Rimuove duplicati con stesso uid logico (stesso date_start+date_end+tipo)."""
    seen = set()
    result = []
    for ev in eventi:
        key = (ev["date_start"], ev["date_end"], ev["is_ferie"], ev["is_indispo"])
        if key not in seen:
            seen.add(key)
            result.append(ev)
    return result

# ── Espansione in giorni ──────────────────────────────────────────────────────

def espandi_in_giorni(eventi):
    """
    Ogni evento (anche multi-day) viene espanso in una entry per giorno.
    Restituisce lista di dict: {date, is_ferie, is_indispo, in_attesa}
    """
    giorni = {}
    for ev in eventi:
        current = ev["date_start"]
        while current <= ev["date_end"]:
            if current not in giorni:
                giorni[current] = {"is_ferie": False, "is_indispo": False, "in_attesa_ferie": False, "in_attesa_indispo": False}
            if ev["is_ferie"]:
                giorni[current]["is_ferie"] = True
                if ev["in_attesa"]:
                    giorni[current]["in_attesa_ferie"] = True
            if ev["is_indispo"]:
                giorni[current]["is_indispo"] = True
                if ev["in_attesa"]:
                    giorni[current]["in_attesa_indispo"] = True
            current += timedelta(days=1)
    return giorni

# ── Merge in blocchi ──────────────────────────────────────────────────────────

def merge_in_blocchi(giorni_dict, festivi_cache):
    """
    Raggruppa i giorni con eventi in blocchi contigui.
    La catena non si rompe se i giorni vuoti in mezzo sono tutti weekend o festivi.
    """
    if not giorni_dict:
        return []

    date_ordinate = sorted(giorni_dict.keys())
    blocchi = []
    
    # Primo blocco
    blocco_start = date_ordinate[0]
    blocco_end = date_ordinate[0]
    blocco_giorni = [date_ordinate[0]]

    for i in range(1, len(date_ordinate)):
        prev = date_ordinate[i - 1]
        curr = date_ordinate[i]

        # Controlla i giorni tra prev e curr (esclusi)
        rompe = False
        giorno_check = prev + timedelta(days=1)
        while giorno_check < curr:
            if not is_giorno_ignorato(giorno_check, festivi_cache):
                rompe = True
                break
            giorno_check += timedelta(days=1)

        if rompe:
            blocchi.append((blocco_start, blocco_end, blocco_giorni))
            blocco_start = curr
            blocco_giorni = [curr]
        else:
            blocco_giorni.append(curr)

        blocco_end = curr

    blocchi.append((blocco_start, blocco_end, blocco_giorni))
    return blocchi

# ── Formattazione blocco ──────────────────────────────────────────────────────

def formatta_blocco(blocco_start, blocco_end, blocco_giorni, giorni_dict):
    has_ferie = any(giorni_dict[g]["is_ferie"] for g in blocco_giorni)
    has_indispo = any(giorni_dict[g]["is_indispo"] for g in blocco_giorni)

    # Emoji
    if has_indispo and has_ferie:
        emoji = "⛔🏖️"
    elif has_indispo:
        emoji = "⛔"
    else:
        emoji = "🏖️"

    # In attesa per tipo
    parti_tipo = []
    if has_indispo:
        in_attesa_indispo = any(giorni_dict[g]["in_attesa_indispo"] for g in blocco_giorni)
        parti_tipo.append("INDISPO (in attesa)" if in_attesa_indispo else "INDISPO")
    if has_ferie:
        in_attesa_ferie = any(giorni_dict[g]["in_attesa_ferie"] for g in blocco_giorni)
        parti_tipo.append("FERIE (in attesa)" if in_attesa_ferie else "FERIE")

    tipo_str = " / ".join(parti_tipo)

    # Data
    if blocco_start == blocco_end:
        data_str = format_data(blocco_start)
    elif blocco_start.month == blocco_end.month:
        data_str = f"{format_data_corta(blocco_start)} → {format_data_corta(blocco_end)} {MESI_ITA[blocco_end.month]}"
    else:
        data_str = f"{format_data(blocco_start)} → {format_data(blocco_end)}"

    return f"   {emoji} {data_str}\n      {tipo_str}"

# ── Generazione nota ──────────────────────────────────────────────────────────

def genera_nota(eventi):
    oggi = date.today()
    mese_corrente = oggi.replace(day=1)
    festivi_cache = {}

    # Filtra mesi passati
    eventi_filtrati = [
        ev for ev in eventi
        if ev["date_end"] >= mese_corrente
    ]

    if not eventi_filtrati:
        return "📋 Calendario Monica\n\nNessun evento trovato."

    giorni_dict = espandi_in_giorni(eventi_filtrati)
    blocchi = merge_in_blocchi(giorni_dict, festivi_cache)

    # Raggruppa blocchi per mese (mese del giorno iniziale)
    blocchi_per_mese = {}
    for blocco_start, blocco_end, blocco_giorni in blocchi:
        mese_key = blocco_start.replace(day=1)
        if mese_key not in blocchi_per_mese:
            blocchi_per_mese[mese_key] = []
        blocchi_per_mese[mese_key].append((blocco_start, blocco_end, blocco_giorni))

    now = datetime.now()
    timestamp = now.strftime("%-d %b %Y ore %H:%M").replace(
        now.strftime("%b"),
        MESI_ITA[now.month][:3]
    )

    righe = [
        "📋 Calendario Monica",
        f"🔄 Aggiornato: {timestamp}",
    ]

    for mese_key in sorted(blocchi_per_mese.keys()):
        nome_mese = MESI_ITA[mese_key.month].upper()
        righe.append(f"\n━━━━━━ {nome_mese} ━━━━━━\n")
        for blocco_start, blocco_end, blocco_giorni in blocchi_per_mese[mese_key]:
            righe.append(formatta_blocco(blocco_start, blocco_end, blocco_giorni, giorni_dict))

    return "\n".join(righe)

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # Carica e unisce i due JSON
    tutti_eventi = []
    for path in [MENSILE_PATH, SETTIMANALE_PATH]:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                    tutti_eventi.extend(parse_eventi(data))
                except json.JSONDecodeError:
                    print(f"Errore parsing {path}")

    tutti_eventi = deduplicа_eventi(tutti_eventi)
    tutti_eventi.sort(key=lambda ev: (ev["date_start"], ev["date_end"]))

    nota = genera_nota(tutti_eventi)

    with open(NOTA_PATH, "w", encoding="utf-8") as f:
        f.write(nota)

    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%dT%H:%M:%S")
    with open(LAST_UPDATE_PATH, "w", encoding="utf-8") as f:
        f.write(timestamp)

    print("✅ nota.txt e last_update.txt generati")
    print("\n--- ANTEPRIMA ---\n")
    print(nota)

if __name__ == "__main__":
    main()
