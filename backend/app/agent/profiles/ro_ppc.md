<!--
Region profile: Romania, PPC Energie (formerly PPC Energie Muntenia).

DATA, NOT CODE. This file is appended verbatim to the extraction agent's system
prompt when app/agent/profiles/registry.toml selects it. A second country is a
second file and a registry row — do not add an `if` to app/agent/ for it.

Labels and vocabulary only. No customer names, addresses, customer codes, POD
codes, meter serials or invoice numbers belong here: they are personal data, and
the model reads them off the bill anyway.
-->

# Region profile: Romania — PPC Energie

Bills are in Romanian. Numbers use a decimal comma and a dot for thousands
(`1.234,56` is 1234.56). Dates are `DD.MM.YYYY`. Currency is `RON` (`lei`).

## Charge labels → charge_kind

Match on the printed label; keep `raw_label` exactly as printed, diacritics
included. A label not listed here is `other` — never force it into a kind.

| Printed label (or close variant) | charge_kind |
| --- | --- |
| `Energie electrică activă`, `Energie activă` | `energy` |
| `Abonament`, `Componenta fixă` | `standing_charge` |
| `Servicii de furnizare`, `Tarif furnizare` | `supply` |
| `Tarif transport - componenta de introducere (TG)`, `Transport TG` | `transmission` |
| `Tarif transport - componenta de extragere (TL)`, `Transport TL` | `transmission` |
| `Tarif distribuție`, `Servicii de distribuție`, `Distribuție JT` | `distribution` |
| `Servicii de sistem`, `Tarif servicii de sistem` | `system_services` |
| `Contribuție cogenerare`, `Contribuția pentru cogenerare de înaltă eficiență` | `cogeneration` |
| `Certificate verzi` | `green_certificates` |
| `Acciză`, `Acciză necomercială` | `excise` |
| `Energie reactivă` | `reactive_energy` |
| `Compensare`, `Plafonare`, `Reducere`, `Discount` | `discount` |
| `TVA` | `vat` |
| `Sold anterior`, `Sold la data emiterii` (only if printed as a line) | `balance` |

## Subtotals

Lines whose label starts with `Total` inside the charge table — `Total energie
electrică activă`, `Total servicii reglementate`, `Total fără TVA` — restate
the lines above them. Extract them as lines with `is_subtotal: true` and the
`charge_kind` of what they total (`other` if mixed). On the standard layout the
seventh and the twelfth lines are subtotals.

## Vocabulary

| Printed | Meaning |
| --- | --- |
| `Factură fiscală`, `Seria … nr. …` | invoice; series and number |
| `Stornare`, `Factură de stornare` | credit note (`document_type: credit_note`) |
| `Stornare a facturii seria … nr. …` | the invoice a credit note reverses → `corrects_invoice_number` |
| `Data emiterii` | `issued_on` |
| `Data scadenței`, `Termen de plată` | `due_on` |
| `Perioadă facturare` | `period_start` – `period_end` |
| `Cod client` | `customer_code` |
| `Cod loc de consum`, `POD`, `Cod POD` | `pod_code` (on the meter reading) |
| `Serie contor` | `meter_serial` |
| `Index vechi` / `Index nou` | `index_previous` / `index_current` |
| `Const.` | `multiplier` |
| `Cantitate de facturat` | the reading's billed `quantity` |
| `Valoare fără TVA`, `Total fără TVA` | `net_amount` |
| `Bază de impozitare TVA`, `Bază impozabilă` | `vat_base` |
| `Valoare TVA` | `vat_amount` |
| `Total factură curentă` | `total_amount` |
| `Sold la data emiterii` | `balance_brought_forward` |
| `Total de plată` | `total_due` (includes the balance) |
| `CIF`, `CUI`, `Cod fiscal` (supplier block) | `provider_tax_id` |

## Mod stabilire index → read_method

| Printed | read_method |
| --- | --- |
| `Citire distribuitor`, `Citire` | `actual` |
| `Autocitire` | `self_read` |
| `Estimare`, `Estimat` | `estimated` |
| `Regularizare` | `regularisation` |
| `Regularizare + Autocitire`, or two methods printed together | `mixed` |

## VAT

Rates seen in this market: 19 % and 21 % (the rate moved from 19 % to 21 %
during the corpus). Read the rate printed on this bill; do not carry one over
from another bill.
