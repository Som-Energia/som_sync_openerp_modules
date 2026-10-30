# Saldos actuals dels comptes ERP de 12 dígits

`export_account_balances_csv.py` obté els camps **`debit`, `credit` i `balance`
calculats pel mateix ERP**, per a una empresa i l'exercici que conté el dia de
l'execució. És una extracció de lectura, independent dels scripts d'obertura.

## Execució

Cal Python 2.7 o Python 3, `erppeek` i `tqdm`. Per a una versió de `tqdm`
compatible amb Python 2.7 i 3.10:

```bash
python -m pip install 'tqdm==4.64.1'
python scripts/export_account_balances_csv.py \
  --company-id 1 \
  --output /tmp/saldos-comptes-erp.csv
```

La connexió usa `Client(**dbconfig.erppeek)` de `scripts/dbconfig.py`.
Reutilitza `opening_common.py` i les utilitats d'imports/relacions de
`opening_01_export_invoices.py`; conserva aquests fitxers al mateix directori.
Amb `pyenv`, pots seleccionar `PYENV_VERSION=2.7.18 python` o
`PYENV_VERSION=3.10.20 python`. El fitxer de sortida ha de ser nou, amb el directori
pare existent. `--batch-size` permet ajustar els lots (200 comptes per defecte).

## Criteri comptable

- Cerca un únic exercici que continga la data actual de la màquina d'execució,
  per a `--company-id`. Si no n'hi ha cap d'específic, cerca un exercici compartit
  (`company_id = False`), com permet l'ERP. Si no n'hi ha cap o n'hi ha diversos,
  acaba amb error.
- Selecciona comptes de l'empresa amb **exactament 12 dígits ASCII**, mantenint
  zeros inicials, comptes inactius i comptes amb saldo zero. Primer obté els
  codis per lots, sense calcular encara els saldos, per determinar el total exacte.
- Llegeix `debit`, `credit` i `balance` per lots amb el context:
  `active_test=False`, `fiscalyear=<ID>`, `date_from=<inici de l'exercici>`,
  `date_to=<hui>` i `state='bydate'`.
- El càlcul natiu inclou els períodes de l'exercici, també els especials
  d'obertura/tancament si els seus apunts compleixen les dates del context.
  No suma l'històric d'altres exercicis ni reconstrueix una obertura que falte.
- Segueix la lògica de l'ERP: en el codi base s'exclouen apunts `draft` i, amb
  `bydate`, es filtren tant la data de l'apunt com la de l'assentament. No afegeix
  una restricció d'assentaments `posted` ni filtra conciliacions.
- Es conserva el valor retornat per l'ERP, incloent la seua consolidació de
  comptes fills. Per això no s'han de sumar indiscriminadament totes les files
  si hi ha comptes de 12 dígits amb descendents o consolidacions superposades.
  Els imports són en moneda de l'empresa, no `amount_currency`.

Per contrastar el resultat, usa el mateix exercici, dates i comptes a l'ERP.
Les lectures RPC per lots no comparteixen una transacció: per obtenir una
comparació estable, usa una còpia consistent o un moment sense moviments.

## Progrés i resultat

La barra `tqdm` va a `stderr` i mostra comptes calculats/total, percentatge,
temps transcorregut, velocitat i estimació restant. **Avança només després de
rebre i validar tot un lot**. Durant la consulta d'un lot queda quieta fins que
l'ERP retorna els saldos. Es tanca també si hi ha un error.

El CSV és UTF-8, separat per `;`, amb una fila per compte i aquestes columnes:

```text
company_id;fiscalyear_id;date_to;account_id;code;name;odoo_account_code;debit;credit;balance
```

Els imports conserven la precisió retornada, sense recalcular ni arrodonir el
saldo a partir del deure/haver. Si falta `odoo_account_code`, la columna queda
buida i el compte s'inclou. La capçalera també es genera quan no hi ha comptes.
El resum informa dels comptes exportats, saldos zero i codis Odoo absents.

Es rebutgen lectures incompletes o duplicades, imports absents/no finits i canvis
de codi/empresa detectats durant l'extracció. El CSV es comença a escriure després
d'haver obtingut tots els saldos. El codi d'eixida és `0` si acaba correctament i
`1` si falla l'extracció o l'escriptura (`2` per arguments invàlids).

## Proves

```bash
PYENV_VERSION=2.7.18 python -m unittest discover -s scripts/tests -v
PYENV_VERSION=3.10.20 python -m unittest discover -s scripts/tests -v
```

Les proves no connecten a l'ERP. Python 2.7 necessita `mock==3.0.5` per a les proves.
