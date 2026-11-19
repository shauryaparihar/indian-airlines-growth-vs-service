# Data issues found in DGCA tables

Every conflict, mismatch, revision, and failed check from the parsers and validators is also stored in the `data_issue` table in PostgreSQL. This page is the readable version.

## Errors found and handled

1. **Air India, Table 1.07, FY 2021-22:** average stage distance printed as 117.5 km. From Table 1.04 it is 90,092 ÷ 76,834 × 1000 = 1,172.6 km.
2. **IndiGo, Table 1.04, FY 2020-21:** load factor printed as 0.7%. The real value is 28,218 ÷ 41,048 × 100 = 68.7%.
3. **Air India, Table 1.04, 2024-25 edition:** the whole weight load factor column is shifted down one row, so each year shows the previous year's value. Found by comparing with the 2023-24 edition and fixed by recomputing from RTK / ATK.
4. **Load factor stored as a 0 to 1 fraction instead of a percent** in one edition's file (IndiGo, Air Deccan, Star Air, SpiceJet), corrected in the next edition. Handled by preferring the latest edition and by recomputing the ratio.
5. **All Scheduled Indian Airlines aggregates, 2016-17 edition:** ton-km figures about 70 times too high for FY 2012-13 to FY 2016-17. Resolved by preferring the later edition.
6. **Table 1.07, FY 2019-20, looks provisional across many airlines:** round numbers where every other year has many decimals, mostly caught through average distance per passenger (about a dozen airlines, 1.3 to 8.4% off). Our recalculated values are used.
7. **Star Air, Table 1.07, FY 2022-23:** average distance per passenger printed as 74.8 against 0.75 recomputed, which looks like a decimal-point error. Flagged only.
8. **A stale file:** the Air Asia 2020-21 domestic history Excel actually holds the 2019-20 table. Logged and not used.

## Suspicious, flagged but not fixed

- Air India, Table 1.04, FY 2014-15: freight (1,00,721 t) equals km flown (1,00,721 thousand), likely a copy error.
- IndiGo, Table 1.07, international, FY 2023-24: average speed 526.9 km/h against about 650 to 680 in other years. It can't be checked without Table 1.05.

## DGCA website problems handled in the download scripts

- Table numbers change between editions: the 10-year domestic table is 1.07 in the oldest editions and 1.04 later, and the coefficients table is 1.10 in 2016-17 and 1.07 later.
- Website titles are wrong for the 2018-19 to 2020-21 editions, so tables are classified by the title inside the Excel file instead.
- The "2020-21" link opens the 2022-23 edition and the "2021-22" link opens the 2020-21 edition. The real 2021-22 edition is not reachable. Coverage impact is small because each edition holds about 10 years.
- A few Excel links return 403 (2016-17 Alliance Air, 2020-21 Air Heritage and Air Taxi, 2022-23 Alliance Air monthly).
- The 2018-19 PDFs extract as reversed text, which is another reason the Excel files are used.

## Other data checks

- Recalculating Table 1.07 ratios from Table 1.04's raw columns logged 37 mismatches over 0.5%.
- Monthly passenger tables: 144 of 146 reports pass their own quarter and year-to-date totals. The other two have no readable table, and their months come from later reports.
- Complaint rates against each report's stated total complaints: 145 of 146 pass.
- Monthly figures summed by fiscal year match the yearly tables within 1% for 48 of 55 airline-years with at least 10 lakh passengers. The Air India family reads 1 to 2% higher in the monthly reports, a perimeter difference, so yearly figures are used for annual growth.
