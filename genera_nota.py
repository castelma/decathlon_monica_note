import json
from datetime import date, datetime, timedelta

GIORNI = [
    "Lunedì", "Martedì", "Mercoledì", "Giovedì",
    "Venerdì", "Sabato", "Domenica"
]
MESI = [
    "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
    "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"
]


# ---------------------------------------------------------------------------
# Festivi aziendali
# ---------------------------------------------------------------------------

def calcola_pasqua(anno):
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


def festivi_aziendali(anno):
    pasqua = calcola_pasqua(anno)
    pasquetta = pasqua + timedelta(days=1)
    return {
        date(anno, 1, 1),    # Capodanno
        pasqua,              # Pasqua
        pasquetta,           # Pasquetta
        date(anno, 8, 15),   # Ferragosto
        date(anno, 12, 25),  # Natale
        date(anno, 12, 26),  # Santo Stefano
    }


def is_giorno_trasparente(d, festivi):
    """Sabato, domenica o festivo aziendale: non rompe la catena di merge."""
    return d.weekday() >= 5 or d in festivi


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def formato_data(d):
    return f"{GIORNI[d.weekday()]} {d.day} {MESI[d.month - 1]}"


def classifica_evento(title):
    t = title.upper()
    if "INDISPO" in t:
        return "INDISPO"
    if "FERIE" in t:
        return "FERIE"
    return None


def is_in_attesa(title):
    return "?" in title


# ---------------------------------------------------------------------------
# Caricamento e normalizzazione eventi
# ---------------------------------------------------------------------------

def carica_eventi(filename):
    """
    Legge un JSON e restituisce lista di dict normalizzati.
    Gli eventi multi-giorno (end_date) vengono espansi giorno per giorno.
    end_date è ESCLUSIVO (convenzione iCalendar) → sottraiamo 1 giorno.
    """
    try:
        with open(filename) as f:
            raw = json.load(f)
    except FileNotFoundError:
        print(f"⚠️  {filename} non trovato, skip")
        return []

    risultato = []
    for e in raw:
        tipo = classifica_evento(e["title"])
        if not tipo:
            continue

        attesa = is_in_attesa(e["title"])
        data_inizio = date.fromisoformat(e["date"])

        if e.get("end_date"):
            # end_date è esclusivo → -1 giorno
            data_fine = date.fromisoformat(e["end_date"]) - timedelta(days=1)
            d = data_inizio
            while d <= data_fine:
                risultato.append({
                    "date": d,
                    "tipo": tipo,
                    "in_attesa": attesa,
                    "uid": e.get("uid", ""),
                })
                d += timedelta(days=1)
        else:
            risultato.append({
                "date": data_inizio,
                "tipo": tipo,
                "in_attesa": attesa,
                "uid": e.get("uid", ""),
            })

    return risultato


# ---------------------------------------------------------------------------
# Merge blocchi consecutivi
# ---------------------------------------------------------------------------

def merge_blocchi(eventi_per_giorno, festivi):
    """
    eventi_per_giorno: dict { date: set of (tipo, in_attesa) }
    Restituisce lista di blocchi merged.
    """
    if not eventi_per_giorno:
        return []

    date_con_eventi = sorted(eventi_per_giorno.keys())
    blocchi = []

    # Inizializza primo blocco
    blocco_start = date_con_eventi[0]
    blocco_end = date_con_eventi[0]
    blocco_tipi_attesa = {}
    for tipo, attesa in eventi_per_giorno[date_con_eventi[0]]:
        if tipo not in blocco_tipi_attesa:
            blocco_tipi_attesa[tipo] = []
        blocco_tipi_attesa[tipo].append(attesa)

    for i in range(1, len(date_con_eventi)):
        data_prec = date_con_eventi[i - 1]
        data_curr = date_con_eventi[i]

        # Controlla se c'è un giorno feriale non festivo vuoto tra i due
        rompe = False
        d = data_prec + timedelta(days=1)
        while d < data_curr:
            if not is_giorno_trasparente(d, festivi):
                rompe = True
                break
            d += timedelta(days=1)

        if rompe:
            blocchi.append({
                "date_start": blocco_start,
                "date_end": blocco_end,
                "tipi_attesa": blocco_tipi_attesa,
            })
            blocco_start = data_curr
            blocco_end = data_curr
            blocco_tipi_attesa = {}
            for tipo, attesa in eventi_per_giorno[data_curr]:
                blocco_tipi_attesa[tipo] = [attesa]
        else:
            blocco_end = data_curr
            for tipo, attesa in eventi_per_giorno[data_curr]:
                if tipo not in blocco_tipi_attesa:
                    blocco_tipi_attesa[tipo] = []
                blocco_tipi_attesa[tipo].append(attesa)

    # Ultimo blocco
    blocchi.append({
        "date_start": blocco_start,
        "date_end": blocco_end,
        "tipi_attesa": blocco_tipi_attesa,
    })

    return blocchi


# ---------------------------------------------------------------------------
# Formattazione blocco
# ---------------------------------------------------------------------------

def formatta_blocco(blocco):
    date_start = blocco["date_start"]
    date_end = blocco["date_end"]
    tipi_attesa = blocco["tipi_attesa"]

    # Emoji
    ha_indispo = "INDISPO" in tipi_attesa
    ha_ferie = "FERIE" in tipi_attesa
    if ha_indispo and ha_ferie:
        em = "⛔🏖️"
    elif ha_indispo:
        em = "⛔"
    else:
        em = "🏖️"

    # Data
    if date_start == date_end:
        data_str = formato_data(date_start)
    else:
        if date_start.month == date_end.month:
            inizio_corta = (
                f"{GIORNI[date_start.weekday()]} {date_start.day}"
            )
            data_str = f"{inizio_corta} → {formato_data(date_end)}"
        else:
            data_str = (
                f"{formato_data(date_start)} → {formato_data(date_end)}"
            )

    riga_data = f"   {em} {data_str}"

    # Label: prima INDISPO poi FERIE
    parti = []
    for tipo in ["INDISPO", "FERIE"]:
        if tipo not in tipi_attesa:
            continue
        if any(tipi_attesa[tipo]):
            parti.append(f"{tipo} (in attesa)")
        else:
            parti.append(tipo)

    riga_label = f"      {' / '.join(parti)}"

    return riga_data, riga_label


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def genera_nota():
    oggi = date.today()
    mese_corrente = oggi.replace(day=1)

    # Carica da entrambi i file
    tutti = carica_eventi("events_mensile.json")
    tutti += carica_eventi("events_settimanale.json")

    # Deduplicazione per (date, tipo) — preferisce approvato su in attesa
    dedup = {}
    for e in tutti:
        key = (e["date"], e["tipo"])
        if key not in dedup:
            dedup[key] = e
        else:
            if not e["in_attesa"]:
                dedup[key] = e

    # Filtra mesi passati
    filtrati = [
        e for e in dedup.values()
        if e["date"] >= mese_corrente
    ]

    if not filtrati:
        with open("nota.txt", "w") as f:
            f.write("📋 Calendario Monica\n🔄 Nessun evento futuro.")
        with open("last_update.txt", "w") as f:
            f.write(datetime.utcnow().isoformat())
        return

    # Costruisci dict { date: set of (tipo, in_attesa) }
    eventi_per_giorno = {}
    for e in filtrati:
        d = e["date"]
        if d not in eventi_per_giorno:
            eventi_per_giorno[d] = set()
        eventi_per_giorno[d].add((e["tipo"], e["in_attesa"]))

    # Festivi per tutti gli anni coinvolti
    anni = {d.year for d in eventi_per_giorno}
    festivi = set()
    for anno in anni:
        festivi |= festivi_aziendali(anno)

    # Merge
    blocchi = merge_blocchi(eventi_per_giorno, festivi)

    # Timestamp italiano
    try:
        from zoneinfo import ZoneInfo
        now_it = datetime.now(ZoneInfo("Europe/Rome"))
    except ImportError:
        now_it = datetime.utcnow() + timedelta(hours=2)

    timestamp = (
        f"{now_it.day} {MESI[now_it.month - 1][:3]} "
        f"{now_it.year} ore {now_it.strftime('%H:%M')}"
    )

    # Costruisci nota
    lines = []
    lines.append("📋 Calendario Monica")
    lines.append(f"🔄 Aggiornato: {timestamp}")

    mese_corrente_str = None
    for blocco in blocchi:
        mese_blocco = MESI[blocco["date_start"].month - 1].upper()
        if mese_blocco != mese_corrente_str:
            lines.append("")
            lines.append(f"━━━━━━ {mese_blocco} ━━━━━━")
            mese_corrente_str = mese_blocco

        lines.append("")
        riga_data, riga_label = formatta_blocco(blocco)
        lines.append(riga_data)
        lines.append(riga_label)

    nota = "\n".join(lines)

    with open("nota.txt", "w") as f:
        f.write(nota)

    with open("last_update.txt", "w") as f:
        f.write(datetime.utcnow().isoformat())

    print("✅ nota.txt e last_update.txt generati")
    print(nota)


genera_nota()
