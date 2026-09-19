# Golden-set fact diagnosis (per domain)

Exact = bench scorer phrase match. Loose = all numbers (or most content words) present.
Classes: PASS / PHRASING (scorer artifact) / GEN_MISS (in context, not in answer) / RETRIEVAL_MISS (not in context).

## Bench path (retrieve + generate, no agent guards)

| Domain | Facts | Exact | Loose | PHRASING | GEN_MISS | RETRIEVAL_MISS |
|---|---:|---:|---:|---:|---:|---:|
| customer_support | 11 | 82% | 91% | 1 | 1 | 0 |
| finance | 14 | 71% | 86% | 2 | 2 | 0 |
| hr | 24 | 83% | 100% | 4 | 0 | 0 |
| legal | 8 | 25% | 25% | 0 | 6 | 0 |
| privacy | 7 | 43% | 43% | 0 | 3 | 1 |

## Agent path (`handle_turn`, incl. policy_math) — HR / Finance only

| Domain | Facts | Exact | Loose | PHRASING | GEN_MISS | RETRIEVAL_MISS |
|---|---:|---:|---:|---:|---:|---:|
| finance | 14 | 57% | 86% | 4 | 2 | 0 |
| hr | 24 | 75% | 100% | 6 | 0 | 0 |

## Per-fact misses (anything not PASS on the bench path)

### `hr_01` (hr) — How many casual leave days do I get per year and how many can I carry forward?
- retrieval confident=True dist=0.20977258682250977 · agent_domain=hr
- **PHRASING** · agent=PHRASING — `5 unused CL days may be carried into the next leave year`
- bench answer: You are entitled to 12 casual leave days per year, credited monthly in advance at 1 day per completed month. Up to 5 unused casual leave days may be carried into the next leave year, with any balance above 5 lapsing on March 31. Casual Leave Entitlement 12 days per leave year Casual Leave Carry-Forw
- agent answer: You get 12 casual leave days per year, credited monthly in advance at 1 day per completed month. Up to 5 unused casual leave days can be carried forward into the next leave year. Casual Leave Entitlement 12 days per year Casual Leave Carry-Forward 5 days per leave year

### `hr_03` (hr) — How long is the probation period for a new hire?
- retrieval confident=True dist=0.1502392292022705 · agent_domain=hr
- **PHRASING** · agent=PHRASING — `extended once, by up to 3 months`
- bench answer: The probation period for new hires (Grades E1 and above) is 6 months, which can be extended by up to 3 months at the discretion of the Reporting Manager and HR Business Partner. Probation Period for Grades E1 and above 6 months  Probation Extension up to 3 months 
- agent answer: The probation period for new hires (Grades E1 and above) is 6 months, which can be extended by up to 3 months at the discretion of the Reporting Manager and HR Business Partner. Probation Period 6 months  Probation Extension up to 3 months 

### `hr_06` (hr) — How many days of earned leave can I encash when I leave the company?
- retrieval confident=True dist=0.2267066240310669 · agent_domain=hr
- **PHRASING** · agent=PHRASING — `up to 30 EL days`
- bench answer: You can encash up to 30 days of earned leave at the time of separation. Maximum Encashment at Separation 30 days
- agent answer: You can encash up to 30 days of earned leave when you separate from the company. Maximum encashment at separation 30 days

### `hr_07` (hr) — How many days can I work from home per week?
- retrieval confident=True dist=0.2497868537902832 · agent_domain=hr
- **PHRASING** · agent=PHRASING — `Grade E2 and above`
- bench answer: You can work from home up to 2 days per week, subject to Reporting Manager approval and team coverage needs. Maximum WFH days per week 2 days
- agent answer: You can work from home up to 2 days per week, subject to Reporting Manager approval and team coverage needs. Maximum WFH days per week 2 days

### `fin_01` (finance) — An employee submits an expense claim for ₹15,000. Who needs to approve it?
- retrieval confident=True dist=0.250116229057312 · agent_domain=finance
- **PHRASING** · agent=PHRASING — `Reporting Manager sign-off required`
- **GEN_MISS** · agent=PHRASING — `₹5,001 – ₹25,000`
- bench answer: The Reporting Manager needs to approve the expense claim for ₹15,000. Claim Value ₹15,000  Required Approval Reporting Manager 
- agent answer: A claim of ₹15,000 falls in the ₹5,001 to ₹25,000 band and requires Reporting Manager sign-off. Claim amount ₹15,000  Approval band ₹5,001 to ₹25,000  Required approval Reporting Manager sign-off 

### `fin_03` (finance) — What is the per diem rate for a business trip to Mumbai?
- retrieval confident=True dist=0.193057119846344 · agent_domain=finance
- **GEN_MISS** · agent=GEN_MISS — `Tier-1`
- bench answer: The per diem rate for a business trip to Mumbai is ₹2,000 per day. Per Diem Rate for Mumbai ₹2,000 per day
- agent answer: The per diem rate for a business trip to Mumbai is ₹2,000 per day. Per Diem Rate for Mumbai ₹2,000 per day

### `fin_06` (finance) — What is the maximum unreceipted expense claim allowed per month?
- retrieval confident=True dist=0.26639068126678467 · agent_domain=finance
- **PHRASING** · agent=PHRASING — `₹1,500 in unreceipted claims per month`
- bench answer: The maximum unreceipted expense claim allowed per month is ₹1,500. Unreceipted Claim Limit ₹1,500 ₹
- agent answer: The maximum unreceipted expense claim allowed per month is ₹1,500. Unreceipted Claim Limit ₹1,500 ₹

### `cs_01` (customer_support) — My toilet is occasionally leaking or running, what should I check?
- retrieval confident=True dist=0.17625701427459717
- **PHRASING** — `flush valve flapper`
- bench answer: Check the trip lever chain for proper slack, adjust the tank water level, and replace the worn or dirty flapper or canister seal. Trip lever chain adjustment Adjust the chain to have roughly one to two links of slack.  Tank water level adjustment Adjust the tank water level to prevent overflow into 

### `cs_04` (customer_support) — How do I register my new Kohler product?
- retrieval confident=True dist=0.13123124837875366
- **GEN_MISS** — `registration`
- bench answer: Users should follow the specific safety and handling instructions provided in the Material Safety Data Sheets (MSDS) for each product, including wearing appropriate personal protective equipment and ensuring proper ventilation. Safety Instructions Wear appropriate personal protective equipment and e

### `priv_02` (privacy) — How do I opt out of having my personal information sold or shared?
- retrieval confident=True dist=0.23769909143447876
- **GEN_MISS** — `Do Not Sell`
- **GEN_MISS** — `Share`
- bench answer: Kohler provides several data subject rights, including the right to access, correct, delete, and transfer personal information, as well as the right to object to processing and withdraw consent. Data Subject Rights Access, correct, delete, transfer, restrict, object, withdraw consent  Contact for Re

### `priv_04` (privacy) — What rights do California residents have regarding their personal data under CCPA?
- retrieval confident=True dist=0.3112518787384033
- **RETRIEVAL_MISS** — `CCPA`
- **GEN_MISS** — `California`
- bench answer: Individuals in Brazil have several rights regarding their personal information, including the right to know what personal information is handled, how it is handled, and the right to access, correct, or delete their personal information. Right to know Individuals can request information about what pe

### `legal_01` (legal) — Are Kohler products compliant with California Proposition 65?
- retrieval confident=True dist=0.18101274967193604
- **GEN_MISS** — `Proposition 65`
- bench answer: The text lists several MSDS documents for various products including Vikrell Repair Kit, Waterless Urinal Cleaner, Waterless Urinal Sealing Liquid, Purefresh Scent Packs, and Kohler Cleaners. Product Vikrell Repair Kit  Product Waterless Urinal Cleaner  Product Waterless Urinal Sealing Liquid  Produ

### `legal_02` (legal) — Does Kohler provide Safety Data Sheets for its products?
- retrieval confident=True dist=0.17426550388336182
- **GEN_MISS** — `Safety Data Sheet`
- **GEN_MISS** — `SDS`
- bench answer: Proposition 65 is a California law that requires businesses to inform Californians about exposures to specific chemicals known to cause cancer or reproductive toxicity. Kohler Kitchen and Bath products are evaluated for compliance with this law, and necessary warnings are provided where required. Wh

### `legal_03` (legal) — What are Kohler's terms and conditions for using kohler.com?
- retrieval confident=True dist=0.1627306342124939
- **GEN_MISS** — `terms`
- bench answer: Kohler offers Product Transparency Documents for green building certifications, which can be found at https://www.us.kohler.com/us/EPD/article/CNT125300002.htm. Product Transparency Documents Available for green building certifications 

### `legal_04` (legal) — Does Kohler offer product transparency documents for green building certifications?
- retrieval confident=True dist=0.025285542011260986
- **GEN_MISS** — `green building`
- **GEN_MISS** — `transparency`
- bench answer: The terms for service warranty non-conformities are described in Section 10.3 of the agreement. Warranty Documentation Review the warranty documentation provided with the product.  Contact Information Call 1-800-4KOHLER (1-800-456-4537).  Call 1-800-4KOHLER (1-800-456-4537) or review the warranty do

- `noanswer_01` (legal) expected no-answer → honesty_ok=False
- `noanswer_02` (privacy) expected no-answer → honesty_ok=True