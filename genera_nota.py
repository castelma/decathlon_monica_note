import json
from datetime import datetime, timedelta

GIORNI = [
    "Lunedì", "Martedì", "Mercoledì", "Giovedì",
    "Venerdì", "Sabato", "Domenica"
]
MESI = [
    "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
    "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"
]

def giorno_nome(data_str):
    d = datetime.strptime(data_str, "%Y-%m-%d")
    return GIORNI[d.weekday()]

def mese_nome(data_str):
    d = datetime.strptime(data_str, "%Y-%m-%d")
    return MESI[d.month - 1]

def formato_data(data_str):
    d = datetime.strptime(data_str, "%Y-%m-%d")
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

def emoji(tipo):
    return "⛔" if tipo == "INDISPO" else "🏖️"

def processa_file(filename):
    with open(filename) as f:
        eventi = json.load(f)

    filtrati = []
    for e in eventi:
        tipo = classifica_evento(e["title"])
        if tipo:
            filtrati.append({
                "date": e["date"],
                "end_date": e.get("end_date"),
                "title": e["title"],
                "tipo": tipo,
                "in_attesa": is_in_attesa(e["title"]),
            })
    return filtrati

def genera_nota():
    eventi = []
    for fname in ["events_mensile.json", "events_settimanale.json"]:
        try:
            eventi += processa_file(fname)
        except FileNotFoundError:
            print(f"⚠️ File {fname} non trovato, skip")

    # Deduplica per date + tipo
    seen = set()
    unici = []
    for e in eventi:
        key = (e["date"], e["tipo"])
        if key not in seen:
            seen.add(key)
            unici.append(e)

    # Ordina per data
    unici.sort(key=lambda x: x["date"])

    # Raggruppa per mese
    mesi = {}
    for e in unici:
        m = mese_nome(e["date"])
        if m not in mesi:
            mesi[m] = []
        mesi[m].append(e)

    # Timestamp aggiornamento ora italiana (UTC+2)
    now_it = datetime.utcnow() + timedelta(hours=2)
    giorno = now_it.day
    mese = MESI[now_it.month - 1][:3]
    anno = now_it.year
    ora = now_it.strftime("%H:%M")
    timestamp = f"{giorno} {mese} {anno} ore {ora}"

    # Costruisci nota
    lines = []
    lines.append("📋 Calendario Monica")
    lines.append(f"🔄 Aggiornato: {timestamp}")

    for mese, evs in mesi.items():
        lines.append("")
        lines.append(f"━━━━━━ {mese.upper()} ━━━━━━")

        for e in evs:
            lines.append("")
            em = emoji(e["tipo"])
            data_inizio = formato_data(e["date"])

            if e["end_date"]:
                data_fine = formato_data(e["end_date"])
                riga = f"   {em} {data_inizio} → {data_fine}"
            else:
                riga = f"   {em} {data_inizio}"

            lines.append(riga)

            label = e["tipo"]
            if e["in_attesa"]:
                label += " (in attesa)"
            lines.append(f"      {label}")

    nota = "\n".join(lines)

    with open("nota.txt", "w") as f:
        f.write(nota)

    with open("last_update.txt", "w") as f:
        f.write(datetime.utcnow().isoformat())

    print("✅ nota.txt e last_update.txt generati")
    print(nota)

genera_nota()
