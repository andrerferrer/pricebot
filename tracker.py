import re, csv, os, yaml, requests
from datetime import datetime, timedelta, timezone

UA = {"User-Agent": "Mozilla/5.0 (compatible; PriceBot/1.0)"}
BR_TZ = timezone(timedelta(hours=-3))

def brl_to_float(s: str) -> float:
    return float(re.sub(r"[^\d]", "", s))/100.0

def extract_price(html: str):
    # 1) JSON-LD "price"
    m = re.search(r'"price"\s*:\s*"(\d+(?:\.\d+)?)"', html, re.I)
    if m: return float(m.group(1))
    # 2) og:price:amount
    m = re.search(r'property="og:price:amount"\s*content="([\d\.]+)"', html, re.I)
    if m: return float(m.group(1))
    # 3) BRL "R$ 5.544,00"
    m = re.search(r'R\$\s*\d{1,3}(?:\.\d{3})*,\d{2}', html)
    if m: return brl_to_float(m.group(0))
    return None

def fetch(url: str) -> str:
    r = requests.get(url, headers=UA, timeout=25)
    r.raise_for_status()
    return r.text

def notify(title: str, body: str):
    # E-mail/Telegram/Slack: adicionar integrações se quiser
    print(f"\n=== ALERT ===\n{title}\n{body}\n=============\n")

def main():
    with open("watchlist.yaml","r",encoding="utf-8") as f:
        items = yaml.safe_load(f)["items"]

    now = datetime.now(BR_TZ).strftime("%Y-%m-%d %H:%M")
    hist_exists = os.path.exists("history.csv")
    with open("history.csv","a",newline="",encoding="utf-8") as hf:
        wr = csv.writer(hf)
        if not hist_exists:
            wr.writerow(["datetime","name","store","url","price_cash"])
        for it in items:
            name, store, url = it["name"], it["store"], it["url"]
            tags = [t.lower() for t in it.get("tags",[])]
            target_cash = float(it.get("target_cash") or 0)

            try:
                html = fetch(url)
                price = extract_price(html)
            except Exception as e:
                print(f"[ERR] {name}: {e}")
                continue

            wr.writerow([now, name, store, url, price])
            print(f"[OK] {name}: R$ {price:.2f}" if price else f"[WARN] {name}: preço não encontrado")

            # condições
            html_low = html.lower()
            is_4060  = ("4060" in tags) or ("4060" in html_low)
            is_5700g = ("5700g" in tags) or ("5700g" in html_low)

            hit = False
            if is_4060 and price and price <= 5500: hit = True
            if is_5700g and price and price <= 2700: hit = True
            if target_cash and price and price <= target_cash: hit = True

            # queda semanal simples: preço atual < mínimo dos últimos 7 registros (exclui o de hoje)
            weekly_drop = False
            try:
                with open("history.csv","r",encoding="utf-8") as rf:
                    rows = list(csv.DictReader(rf))
                past = [float(r["price_cash"]) for r in rows if r["name"]==name]
                if len(past) >= 2:
                    prior = past[:-1][-7:]  # últimos 7 antes do atual
                    if prior and price and price < min(prior):
                        weekly_drop = True
            except Exception:
                pass

            if hit or weekly_drop:
                cond = []
                if is_4060 and price and price <= 5500: cond.append("RTX4060<=5500")
                if is_5700g and price and price <= 2700: cond.append("5700G<=2700")
                if target_cash and price and price <= target_cash: cond.append(f"meta<= {target_cash:.0f}")
                if weekly_drop: cond.append("queda semanal")

                title = f"[ALERTA] {name}"
                body  = f"Loja: {store}\nURL: {url}\nPreço PIX: R$ {price:.2f}\nCondição: {', '.join(cond)}"
                notify(title, body)

if __name__ == "__main__":
    main()
