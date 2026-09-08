# Power BI build recipe — `hamburg-delays.pbix`

Power BI Desktop can't be scripted from this repo, so this is the paint-by-numbers
version: paste the query, paste the measures, drop the visuals, save as
`powerbi/hamburg-delays.pbix`, export a PNG or two into `../images/`.

Data source: `../hamburg_delays.csv` (repo root), schema in the main README.

---

## 1. Parameter → then Get Data → Blank query → Advanced Editor

First make a parameter so the path isn't baked into visuals:
**Home → Manage Parameters → New** → name `RepoRoot`, type Text, current value
`C:\Users\emira\Projects\db-hamburg-delays` (change per machine).

Then **Get Data → Blank Query → Advanced Editor** and paste:

```m
let
    Source = Csv.Document(
        File.Contents(RepoRoot & "\hamburg_delays.csv"),
        [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]
    ),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    Typed = Table.TransformColumnTypes(Promoted, {
        {"check_time", type datetime},
        {"train_id", type text},
        {"category", type text},
        {"line", type text},
        {"train_no", type text},
        {"planned_arr", type datetime},
        {"actual_arr", type datetime},
        {"delay_min", Int64.Type},
        {"cancelled", Int64.Type},
        {"platform", type text},
        {"origin", type text},
        {"source", type text}
    }),
    // drop stale "zombie" echoes: planned time >12h from when we polled
    NoZombies = Table.SelectRows(Typed, each
        [planned_arr] = null or [check_time] = null
        or Duration.TotalHours(Number.Abs([check_time] - [planned_arr])) <= 12),
    AddDelayPos = Table.AddColumn(NoZombies, "delay_pos",
        each if [delay_min] = null then null else List.Max({[delay_min], 0}), Int64.Type),
    AddHour = Table.AddColumn(AddDelayPos, "arr_hour",
        each if [planned_arr] = null then null else Time.Hour([planned_arr]), Int64.Type),
    AddDate = Table.AddColumn(AddHour, "arr_date",
        each if [planned_arr] = null then null else DateTime.Date([planned_arr]), type date),
    AddDOW = Table.AddColumn(AddDate, "arr_weekday",
        each if [planned_arr] = null then null else Date.DayOfWeekName([planned_arr]), type text),
    AddOnTime = Table.AddColumn(AddDOW, "on_time",
        each if [delay_pos] = null then null else [delay_pos] < 6, type logical)
in
    AddOnTime
```

Name the query **`delays`**. Load it.

*(Optional but nice: also build a Date table — `Calendar(MIN('delays'[arr_date]), MAX('delays'[arr_date]))` — mark it as a date table and relate `Date[Date] → delays[arr_date]`.)*

---

## 2. Measures (New measure, one per line)

```dax
Trains rated       = COUNTROWS(FILTER('delays', NOT ISBLANK('delays'[delay_pos])))
Avg delay (min)    = AVERAGE('delays'[delay_pos])
Median delay (min) = MEDIAN('delays'[delay_pos])
P90 delay (min)    = PERCENTILE.INCL('delays'[delay_pos], 0.9)
On-time %          = DIVIDE(COUNTROWS(FILTER('delays', 'delays'[on_time] = TRUE())), [Trains rated])
Delayed >15 %      = DIVIDE(COUNTROWS(FILTER('delays', 'delays'[delay_pos] > 15)), [Trains rated])
Cancellations      = SUM('delays'[cancelled])
Cancel %           = DIVIDE([Cancellations], COUNTROWS('delays'))
Worst line delay   = MAXX(VALUES('delays'[line]), [Avg delay (min)])
```

Format `On-time %`, `Delayed >15 %`, `Cancel %` as percentage; the rest as whole/1-dp number.

---

## 3. Report page — "Hamburg Hbf reliability"

Background `#F7F7F8`, one 1280×720 page.

| # | Visual | Fields | Notes |
|---|---|---|---|
| 1 | 4× Card (top row) | `Avg delay (min)`, `On-time %`, `P90 delay (min)`, `Cancellations` | KPI strip |
| 2 | Clustered column | Axis `arr_hour` (0–23), Value `Avg delay (min)` | headline: delay by hour of day |
| 3 | Bar chart | Axis `line`, Value `Avg delay (min)`, sort desc | worst lines; data-color rule: >5 min → orange `#F97316`, else blue `#3B82F6` |
| 4 | Line chart | Axis `arr_date`, Value `Avg delay (min)` + `On-time %` (secondary axis) | trend over time |
| 5 | Column chart | Axis `arr_weekday` (sort Mon→Sun), Value `Avg delay (min)` | weekday pattern |
| 6 | Matrix | Rows `category`, Values `Trains rated`, `Avg delay (min)`, `On-time %`, `Cancellations` | breakdown table |
| 7 | Slicers | `source` (default = `live`), `category`, `arr_date` (between) | let `legacy` be opt-in |
| 8 | Histogram / column | Axis = binned `delay_pos` (bin size 5), Value `Trains rated` | delay distribution |

Title textbox: **"Hamburg Hbf — Arrival Reliability"**, subtitle
"Deutsche Bahn Timetables API · updated every 15 min".

---

## 4. Save & publish
1. Save as `powerbi/hamburg-delays.pbix`.
2. Export the report page: **File → Export → Export to PDF**, or screenshot the
   canvas → save as `images/dashboard-overview.png` and reference it in the README.
3. Commit the `.pbix` and the PNG.

> Refresh model: **Home → Refresh** after each `git pull` picks up new rows.
> The Excel-era `legacy` rows carry no `line`/`category`/`origin`; the `source`
> slicer defaulting to `live` keeps them out of the headline numbers.
