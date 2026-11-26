"""Homicídios por município (residência), SIM/DataSUS, anos fechados.

Agressões = causa básica CID-10 X85 a Y09. Gera dados/homicidios.json uma vez (recalcular quando sair novo ano):
{"anos": "2022–2024", "por_mun": {"310620": n_obitos, ...}}
Rodar: python -m robo.homicidios
"""
import ftplib
import io
import json
import re
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARQ = RAIZ / "dados" / "homicidios.json"
ANOS = (2022, 2023, 2024)
UFS = ("AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO").split()
_AGRESSAO = re.compile(r"^(X8[5-9]|X9\d|Y0\d)")


def construir():
    from dbfread import DBF
    from pyreaddbc import dbc2dbf

    por_mun = {}
    ftp = ftplib.FTP("ftp.datasus.gov.br", timeout=120)
    ftp.login()
    ftp.cwd("/dissemin/publicos/SIM/CID10/DORES")
    with tempfile.TemporaryDirectory() as tmp:
        for ano in ANOS:
            for uf in UFS:
                nome = f"DO{uf}{ano}.dbc"
                dbc, dbf = Path(tmp) / nome, Path(tmp) / (nome[:-4] + ".dbf")
                buf = io.BytesIO()
                ftp.retrbinary(f"RETR {nome}", buf.write)
                dbc.write_bytes(buf.getvalue())
                dbc2dbf(str(dbc), str(dbf))
                n = 0
                for r in DBF(str(dbf), encoding="latin-1", load=False):
                    if _AGRESSAO.match(str(r.get("CAUSABAS") or "")):
                        mun = str(r.get("CODMUNRES") or "")[:6]
                        por_mun[mun] = por_mun.get(mun, 0) + 1
                        n += 1
                print(f"  {nome}: {n} homicídios")
                dbc.unlink()
                dbf.unlink()
    ftp.quit()
    d = {"anos": f"{ANOS[0]}–{ANOS[-1]}", "qtd_anos": len(ANOS), "por_mun": por_mun}
    ARQ.write_text(json.dumps(d), encoding="utf-8")
    print(f"total: {sum(por_mun.values())} homicídios em {len(por_mun)} municípios")


class Homicidios:
    def __init__(self, pop_por_cod):
        self.ok = ARQ.exists()
        if not self.ok:
            return
        d = json.loads(ARQ.read_text(encoding="utf-8"))
        self.anos, self.qtd, self.por_mun = d["anos"], d["qtd_anos"], d["por_mun"]
        pop6 = {c[:6]: p for c, p in pop_por_cod.items()}
        tot_pop = sum(pop6.values())
        self.media_br = sum(self.por_mun.values()) / self.qtd / tot_pop * 1e5 if tot_pop else None
        self.pop6 = pop6

    def de(self, cod):
        """(taxa anual por 100 mil, vezes a média do país, óbitos no período) ou None."""
        if not self.ok or not self.media_br:
            return None
        c6 = str(cod)[:6]
        n, pop = self.por_mun.get(c6, 0), self.pop6.get(c6)
        if not pop:
            return None
        taxa = n / self.qtd / pop * 1e5
        return taxa, taxa / self.media_br, n


if __name__ == "__main__":
    construir()
