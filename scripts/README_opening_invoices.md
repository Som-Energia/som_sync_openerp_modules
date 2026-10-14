# Assajos del traspàs de factures obertes

Seguiment: [issue ERP #77](https://github.com/Som-Energia/som_sync_openerp_modules/issues/77).

## Primera peça: extracció i diagnòstic

`export_opening_invoices.py` és un script independent (Python 3.7 o superior),
que utilitza `erppeek`, igual que els altres scripts del repositori, sense
necessitat d'arrencar Odoo. La connexió es crea amb
`Client(**dbconfig.erppeek)` i les consultes amb `client.execute(...)`.
S'executa fora del procés de l'ERP i no s'importa des de `__init__.py`.

L'objectiu és obtenir el punt de partida reproduïble per a les proves
d'integració: carregar les factures obertes i després generar cobraments,
remeses, devolucions i fraccionaments a l'ERP de proves, comprovant que la
sincronització real els aplica correctament a Odoo.

### Preparació

Treballa contra una **còpia consistent i sense moviments durant l'extracció** de
l'ERP. Un conjunt de consultes XML-RPC no proporciona una transacció comuna;
l'script no congela una base de dades viva. La data de tall ha de correspondre a
aquesta còpia: no es reconstrueix un pendent històric ni es prediu el desembre.

La selecció inclou:

- Factures `open` o `paid` amb `residual != 0`, de l'empresa indicada.
- Factures referenciades per acords de fraccionament actius, encara que tinguin
  residual zero: el deute pot estar traspassat a quotes amb apunts propis.
- Acords i quotes relacionats, incloses les parts ja liquidades.
- Apunts de les factures, acords, liquidacions i cancel·lacions referenciades.
- Comptes dels apunts recollits per facilitar la revisió.

L'script rebutja còpies amb assentaments comptabilitzats posteriors al tall,
factures seleccionades amb data absent o posterior, acords posteriors i lectures
incompletes. Aquestes comprovacions **no substitueixen la còpia consistent**.
Si no existeix el model de fraccionaments, ho indica al JSON; si existeix però no
es pot consultar, l'extracció falla.

### Execució

Configura `scripts/dbconfig.py`, diccionari `erppeek`, amb les dades de la còpia
de proves (`server`, `db`, `user` i `password`), igual que per als altres scripts.
Cal tenir `erppeek` instal·lat en l'entorn Python utilitzat.

Des de l'arrel del repositori, amb un directori pare de sortida ja existent:

```bash
python3 scripts/export_opening_invoices.py \
  --cutoff 2026-10-14 \
  --company-id 1 \
  --snapshot-reference copia-erp-2026-10-14 \
  --output /tmp/obertura-2026-10-14
```

Substitueix la data d'exemple per la data de la còpia utilitzada. Per al traspàs
definitiu, el tall serà `2026-12-31`. Es pot ajustar `--batch-size` (200 per defecte).

Selecciona un intèrpret Python 3.7 o superior, encara que l'ERP utilitzi una
versió antiga. Amb `pyenv`, pots substituir `python3` per
`PYENV_VERSION=3.10.20 python`; aquesta és la versió emprada per verificar l'script.
La sintaxi respecta els hooks de validació amb Python 2.7 del repositori, però
l'execució de l'script requereix Python 3.

### Resultat

- `opening_invoices.json`: registres originals, metadades d'origen i del tall,
  disponibilitat dels fraccionaments, diagnòstics i totals de residual per tipus,
  moneda, compte i tercer. Els registres conserven els identificadors **ERP**;
  encara no són un payload de la API d'Odoo.
- `invoices.csv`: número, tercer, compte, moneda, dates, total original, residual
  i indicador d'acords actius. Utilitza el mòdul CSV per conservar correctament
  separadors, salts de línia i accents.
- `opening_invoices.sha256`: empremta del JSON per identificar-ne el contingut.

Els totals es calculen amb `Decimal` i es guarden com a text. Els imports dels
registres originals es conserven tal com els retorna l'ERP. El residual manté el
signe de l'ERP i els totals separen tipus i monedes: no són un saldo net de major.
**No se sumen residuals i quotes**: pot haver-hi imports traspassats o superposats
que cal analitzar. El JSON queda marcat `ready_for_import: false`.

Cada execució exigeix un directori nou per no sobreescriure una foto anterior.
Conserva la mateixa còpia de l'ERP per al quadrament inicial. Quan després generis
esdeveniments a l'ERP de proves, compara Odoo amb l'estat evolucionat d'aquella
còpia un cop processades les cues.

## Peces següents

1. Analitzar aquesta extracció amb casos reals de fraccionaments i conciliar-la
   amb els saldos globals, incloent-hi les partides sense factura.
2. Acordar el diari, la data comptable i la contrapartida d'obertura.
3. Implementar la càrrega a Odoo, la resolució de dades mestres i els mapatges
   `odoo.sync`, amb represa i sense duplicats.
4. Preservar les dependències necessàries per a devolucions de moviments previs
   al tall i definir la frontera amb les cues històriques.
5. Afegir el comparador ERP/Odoo i executar els casos d'integració de punta a punta.

La primera peça encara no importa ni compara dades amb Odoo, ni exporta tot el
major o totes les remeses històriques. No modifica els dos sistemes.

## Verificació local

```bash
python3 -m unittest discover -s scripts/tests -v
```
