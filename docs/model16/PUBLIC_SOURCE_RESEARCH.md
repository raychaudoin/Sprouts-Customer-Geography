# MODEL-16 public-source research

This record describes target-blind source discovery. A proposed source or successful
HTTP response is not feature admission. The frozen feature catalog and acquisition
receipts identify the actual analytical inputs. This research never reads protected
inputs or targets and sends no protected locations to public services.

## Temporal and source-selection rule

The primary historical track requires a documented release available by December 31
before the forecast year. Reference year and release year are distinct. Public files
downloaded later must retain a defensible historical version; a current revision of an
old reference year does not establish what was available at the historical cutoff.
Store openings, road changes, development, traffic and remote sensing require this
check particularly carefully. A structural fixed snapshot requires an explicit
exception rationale and cannot silently become historically honest validation.

Admission also requires free lawful reuse, reproducible access, MI/WI comparable
definitions, explicit geographic reconciliation, field allowlisting, missingness,
and a bounded transformation chosen before development targets. Direct protected
characteristics and protected-class disaggregations are excluded from scoring.
Suppressed business employment, missing roads, and absent traffic stations are not
zeros. Geography mismatch is not solved by truncating a later GEOID to an earlier one.

## Bounded discovery queue

The following are hypotheses and discovery targets, not claims that data have been
retrieved or admitted. Verified findings are recorded separately below.

| Family | Official discovery source | Candidate signal and bounded treatment | Admission issue to resolve |
| --- | --- | --- | --- |
| Household economics, housing, mass and change | [Census ACS](https://www.census.gov/programs-surveys/acs) | Lagged five-year detailed estimates; separate household mass, income, housing, commute and overlapping-vintage change | MOE, denominator validity, release cutoff, tract keys; no protected-class disaggregations |
| Jobs, daytime population and commuting flows | [LEHD data](https://lehd.ces.census.gov/data/) | Workplace and resident jobs, sector mix, inflow/outflow, OD travel distance | Pin release and schema; current historical-year files may be revised; block geography changes |
| Built environment and accessibility | [EPA Smart Location Mapping](https://www.epa.gov/smartgrowth/smart-location-mapping) | Small explicit set of intersection, employment mix, destination accessibility and transit variables | Obtain 2021 release and source years; reconcile 2010 block groups with current tract geography spatially |
| Retail/business context | [County Business Patterns](https://www.census.gov/programs-surveys/cbp.html) | County grocery establishments, restaurant/retail mix and establishment intensity | County context cannot represent site-level competition/co-tenancy; suppression and NAICS transitions |
| Food access | [USDA Food Access Research Atlas](https://www.ers.usda.gov/data-products/food-access-research-atlas/download-the-data) | Historical overall low-access population share and low-vehicle food access | Food desert designation is not a customer-fit label; retain original tract geography and no protected-class fields |
| Roads, traffic and hourly movement | [FHWA TMAS](https://www.fhwa.dot.gov/policyinformation/tables/tmasdata/), [Michigan DOT](https://www.michigan.gov/mdot/travel/traffic-data), [Wisconsin DOT](https://wisconsindot.gov/Pages/projects/data-plan/traf-counts/default.aspx) | Annual volume and stable AM/PM directional ratios, historical road topology | Comparable year/count method, station selection and spatial coverage; road counts are not footfall |
| Travel-time accessibility | [OpenStreetMap history](https://wiki.openstreetmap.org/wiki/Planet.osm/full) | Historical road-network distances and bounded isochrones | Historical snapshot/license, turn rules/speeds, routing reproducibility; current OSM cannot establish past roads |
| POIs, competition and co-tenancy | [Overture releases](https://docs.overturemaps.org/release/latest/) | Historical grocery/retail/fitness category counts and nearest distances | Historical retained snapshot, completeness, category continuity, ODbL/attribution; current POIs leak later openings |
| Land use and buildings | [MRLC/NLCD](https://www.mrlc.gov/data) | Prior-release developed-cover and imperviousness around locations | Land-cover reference year versus release year; raster processing and nodata; no household identities |
| Nighttime activity | [Earth Observation Group VIIRS](https://eogdata.mines.edu/products/vnl/) | Prior-release annual stable radiance and lit-area share | Free download/reuse terms, release/version, cloud/stray-light handling and nodata; lights are not retail sales |
| Housing growth and permits | [Census Building Permits Survey](https://www.census.gov/construction/bps/index.html) | County lagged permitted units per existing housing unit | Permit is authorization, not completion; coverage changes, revisions and publication timing |
| Regional growth and employment | BEA regional accounts and BLS QCEW | Lagged county real income/employment change | Historic release preservation, suppression, regional/coarse geography; redundant predictors controlled in folds |
| Transit and local permits/licenses | Official regional GTFS and local open-data portals | Prior-published transit supply or permit volume if harmonizable | Comparable multi-market coverage and historical feeds; incomplete cities are not zero-service/zero-permit |
| Unconventional lawful signals | Official, versioned sources only | A business hypothesis and no direct protected-characteristic input are required | Same legality, temporal, reproducibility, sample-size and nested-validation tests; no exclusion based solely on sensitivity |

## Verified findings, retrieved September 13, 2026

The acquisition adapter is `model16/context_research.py`. Public documents, source
bytes and URL/retrieval-time/HTTP-date/SHA-256 receipts stay in the ignored public
cache. `model16/public_context.py` supplies the supplemental feature definitions and
local spatial joins. This research never used protected observations or targets.
The final execution report supplies actual feature coverage and grouped validation;
research discovery alone does not establish empirical contribution.

### Complete source inventory and ACS/TIGER historical track

`config/model16/PUBLIC_SOURCE_MANIFEST.json` records all **179** bounded acquisition
jobs: **174** retrieved and hash-verified, and five recorded discovery failures.
The supplemental subset separately has 59 jobs and 54 retrieved sources. Every
complete-manifest entry records requested and resolved URLs, byte length, SHA-256,
retrieval time, available server date, schema, geography, analytical role and
admission or rejection reason. `public_sources.verify_manifest` rehashes the actual
cache and compares the entire saved manifest. Discovery documents and live-service
QA are separately labeled; their retrieval does not become historical input data.

The primary ACS source is the Census public
[table-based summary-file archive](https://www2.census.gov/programs-surveys/acs/summary_file/).
National pipe-delimited detailed tables preserve estimates and margins of error;
the adapter filters Michigan/Wisconsin tract rows locally and retains only the
allowlisted economic and household quantities. The year-specific Census API group
metadata validates column labels and definitions. It is current schema evidence,
not a claim of an archived historical response or a target-year observation.
These are Census public statistical products, with Census/ACS attribution.

| Forecast year | ACS primary estimate vintage | Earlier vintage for descriptive growth | Analytical geometry |
| --- | --- | --- | --- |
| 2024 | 2022 five-year ACS | 2021 | Fixed TIGER2023 |
| 2025 | 2023 five-year ACS | 2022 | Fixed TIGER2023 |
| 2026 | 2023 five-year ACS | 2022 | Fixed TIGER2023 |

The 2021 raw-table receipts show November 2022 modifications; 2022 tables show
October 2023; the admitted 2023 tables precede January 2025. The exact timestamps
and checksums remain in the manifest. The two
[TIGER2023 state tract files](https://www2.census.gov/geo/tiger/TIGER2023/TRACT/)
have November 23, 2023 modification dates. All primary geometries use those fixed
polygons and published internal points; exact tract-key reconciliation is required
against each ACS vintage. A later geometry is never silently joined by a prefix.

The initially retrieved ACS2024 table files are **rejected from primary historical
scoring**: all carry January 29, 2026 server modification dates. A 2024 reference
year or normal release schedule does not prove those exact revised bytes existed
before 2026. TIGER2024 files carry June 27, 2025 modification dates, too late for
the 2025 cutoff. TIGER2025 is timely for 2026 but is also excluded to retain the
same pre-development geometry contract across cohorts. Those retrieved files and
their metadata remain in the rejection record and never enter the final matrix.
This means **2026 receives no additional ACS vintage**; temporal evaluation cannot
be described as testing an ACS2024 refresh.

HTTP Last-Modified is publisher-provided distribution evidence, not cryptographic
proof of an archived snapshot. The implementation retains that limitation, checks
dates against every assigned forecast cutoff, and rejects later revisions where
pre-cutoff bytes were not established. The source manifest is bound to the ACS
matrix sidecar, the complete feature package, and the feature/library freeze.

### EPA Smart Location Database version 3

The [official page](https://www.epa.gov/smartgrowth/smart-location-mapping) explicitly
identifies the current SLD release as 2021 and links the
[original version 3 archive](https://edg.epa.gov/EPADataCommons/public/OA/SLD/SmartLocationDatabaseV3.zip).
The retrieved ZIP is 553,251,612 bytes, with HTTP Last-Modified June 8, 2021. Its
geodatabase data files are dated April 30, 2021; the included guide is dated June 3,
2021. The separately linked [technical guide](https://www.epa.gov/system/files/documents/2023-10/epa_sld_3.0_technicaldocumentationuserguide_may2021_0.pdf)
states version 3.0, updated June 2021. The later website path is not the source's
analytical vintage.

The public [service schema](https://geodata.epa.gov/arcgis/rest/services/OA/SmartLocationDatabase/MapServer/1?f=pjson)
and state-wide queries were also retrieved, with complete object-ID inventory
reconciliation: 8,159 Michigan and 4,473 Wisconsin block groups. `GEOID20` in this
service means a 2018 block-group identifier, **not** 2020 Census geography. The
database uses 2019 block-group boundaries, derived from the 2010-era Census system.
Spatial joins therefore use source polygons, never a modern tract-prefix join.

| Selected public quantities | Underlying vintages | Interpretation and important limitation |
| --- | --- | --- |
| `TotEmp`, `Workers`, `E5_Ret`, `E5_Off` | 2017 LEHD WAC/RAC | Workplace mass, resident-worker balance and retail/office job mix; jobs are not unique shoppers or observed visits |
| `D3A`, `D3B` | 2018 HERE road network, published as EPA indicators in 2021 | Road and intersection density; no raw HERE network was acquired |
| `D4D` | Historical GTFS used in the 2020 build | Evening peak transit frequency per square mile; old/incomplete service feeds |
| `D5AR`, `D5BR` | 2017 employment and 2020 network/transit analysis | Time-decayed jobs accessible within 45 minutes; EPA's public derived measures, not a new commercial routing query |

The EPA product is a publicly supplied government statistical product explicitly
named in the Work Order. Some upstream HERE/TravelTime inputs were commercial.
This implementation admits EPA's published indicators, records their lineage, and
does not acquire, redistribute, or call those proprietary raw products. It does not
claim every upstream input was public. The guide describes SLD as a publicly
available data product and service; the official page supplies unrestricted download
and service links. No indicator-specific prohibition on use was found in the
retrieved documentation.

The same current service and original archive also contain Smart Location Calculator VMT/GHG
outputs, with direct race/sex regressors. Those outputs, their coefficients,
`White`, `Male`, working-age population access (`D5AE`, `D5BE`) and all other
unapproved fields are excluded. The request and analytical record use an explicit
field allowlist. The implementation reads the original FileGDB as its analytical
authority through the pinned `pyogrio==0.11.1` raw array API. The source contains
8,205 Michigan and 4,489 Wisconsin block groups: 46/16 additional original groups
are absent from the current service. All 16 allowed numeric quantities match within
1e-12 absolute/relative tolerance across the 8,159/4,473 common groups. The original
geography uses NAD83 Albers ESRI:102039; both states pass with zero geometry repairs.
The service is therefore QA only, and its omissions never determine the cohort.

The guide's page 23, footnote 65, states that `-99999` in transit variables can mean
exceeded distance thresholds, absent GTFS coverage, or shoreline/water block groups
without land, population or jobs. It is retained as missing, never zero. Pages 22–24
document that only 499 of 573 transit feeds had sufficient schedule information.
The guide also documents pandemic-era service changes and use of older feeds where
they recovered additional accessibility. These are stale descriptive accessibility
measures, not current traffic or complete transit access.

Nine bounded features use employment totals, job/resident balance, two sector
shares, area-weighted road/intersection/transit-frequency density, and two anchor
accessibility values. Five-mile membership uses historical polygon representative
points in equal-area projection, forcing the containing polygon. Negative/missing
constituents remain missing. The retrieved GeoJSON required 15 tiny Wisconsin
polygon repairs, with maximum relative area change 0.0000008226; the general rule
allows deterministic polygon-only `make_valid` repairs up to one part per million
of area and fails closed beyond that. Michigan required no repair. Original archive
geometry takes precedence if used directly.

### Census County Business Patterns

Actual national county files were downloaded and schema-checked:

| Forecast year | County business reference year | Preserved file date | Official file |
| --- | --- | --- | --- |
| 2024 | 2021 | April 27, 2023 | [cbp21co.zip](https://www2.census.gov/programs-surveys/cbp/datasets/2021/cbp21co.zip) |
| 2025 | 2022 | June 27, 2024 | [cbp22co.zip](https://www2.census.gov/programs-surveys/cbp/datasets/2022/cbp22co.zip) |
| 2026 | 2023 | June 26, 2025 | [cbp23co.zip](https://www2.census.gov/programs-surveys/cbp/datasets/2023/cbp23co.zip) |

These are the HTTP modification dates of the retrieved data bytes, corroborated by
the corresponding official directory listings, not a claim about initial release
day. All precede the applicable forecast-year cutoff. A later file revision fails
the loader's temporal check. The parser selects MI/WI `fipstate`, `fipscty`, `naics`
and `est` only. Four county features use grocery establishment count and retail,
food-service and fitness shares of all establishments, with predeclared NAICS codes
`445110`, `44----`, `722///`, `713940` and `------`. Suppressed/noise-infused
employment and payroll quantities are unused. Absent industry rows remain missing.
These are public Census aggregates; county mix is coarse context and does not
establish nearest competitor, store brand, shopping-center co-tenancy or site traffic.

### USDA Food Access Research Atlas 2019

The [official download page](https://www.ers.usda.gov/data-products/food-access-research-atlas/download-the-data)
identifies the 2019 product, now labeled Large Retailer Access Map, as last updated
April 27, 2021. The linked
[CSV ZIP](https://www.ers.usda.gov/media/5627/2019-large-retailer-access-map-lram-formerly-known-as-the-food-access-research-atlas-fara-data.zip?v=23010)
contains `ReadMe.csv`, `VariableLookup.csv` and the data table. The internal readme
confirms initial release April 2021. The new 2025 SNAP retailer map on the same page
is not substituted for this source.
All three archived CSV members are dated April 21, 2021; a later member date fails
the source-version check rather than relying on the old reference-year label alone.

Only `CensusTract`, `Pop2010`, `OHU2010`, `lapophalf`, and `lahunvhalf` enter the
analytical records. Two features describe the containing historical tract's share
of population, and share of households without vehicles, more than half a mile
from a supermarket. Counts are divided by the corresponding total rather than
misinterpreting published 0–100 percentage fields as fractions. The measures are
historical resident access, not Sprouts customer fit, competitor identity, or current
food-desert designation. Race, age and ethnicity disaggregations are not scored.

There are 2,756 Michigan and 1,392 Wisconsin source rows. Historical
[Michigan](https://www2.census.gov/geo/tiger/TIGER2019/TRACT/tl_2019_26_tract.zip) and
[Wisconsin](https://www2.census.gov/geo/tiger/TIGER2019/TRACT/tl_2019_55_tract.zip)
TIGER polygons contain 2,813 and 1,409 tracts. The 57/17 polygons without source rows
remain explicit missingness. A containing-tract join avoids propagating an omitted
shoreline/zero-population tract across an otherwise observed radial catchment;
unmatched anchors remain missing. This definition was chosen using public source
coverage, before any protected outcomes.

### Archived LODES7 2019 incoming commuting flows

The [retained LODES7 archive](https://lehd.ces.census.gov/data/lodes/LODES7/) and
[format 7.5 guide](https://lehd.ces.census.gov/data/lodes/LODES7/LODESTechDoc7.5.pdf)
provide a historical alternative to backdating current LODES8 files. The guide,
revision October 20, 2021, explicitly describes 2019 TIGER/Line geography with
2010 Census blocks and data through 2019. Raw 2019 data rows were created October
18, 2021. Version/creation dates are distinct; file publication evidence is retained
as well as each row's creation marker.
Both state version files identify data vintage `20211018_1647`, format 7.5. All six
uncompressed data files match the official Census SHA-256 manifests, in addition
to receipt verification of the downloaded gzip bytes.

For [Michigan](https://lehd.ces.census.gov/data/lodes/LODES7/mi/od/) and
[Wisconsin](https://lehd.ces.census.gov/data/lodes/LODES7/wi/od/), main plus auxiliary
`JT00` OD files were acquired. Main files cover within-state home/work pairs;
auxiliary files add residents of other states working in the selected state. WAC
`S000_JT00` files independently validate workplace-job totals. The parser retains
only home/work block identifiers, total jobs and the creation date. Age, race,
ethnicity, education, sex, earnings and sector disaggregations are not used.

| Public-state source check | Michigan | Wisconsin |
| --- | ---: | ---: |
| Main block OD pairs | 3,894,952 | 2,527,827 |
| Auxiliary block OD pairs | 73,684 | 107,866 |
| WAC workplace blocks | 67,697 | 53,351 |
| Workplace tracts | 2,755 | 1,394 |
| Total jobs | 4,337,930 | 2,879,941 |
| OD main + auxiliary versus WAC total, separately for every workplace tract | Exact match | Exact match |

Two bounded commuting-flow features use the same original tract support:

- The fraction of incoming jobs whose home tract lies outside the workplace
  five-mile support. Auxiliary origins are included even when they lie outside
  MI/WI. This is a workplace inflow measure, not complete resident outflow.
- The job-weighted straight-line distance between historical tract internal points.
  Distance is reported only when at least 95% of jobs have both endpoints in the
  acquired MI/WI geometry. Other-state origins remain in the coverage denominator
  and are never assigned zero distance. Within-tract trips have zero distance at
  this coarse resolution; sub-tract travel is unresolved. This is not driving
  distance, actual travel time or a mobile-device movement measurement.

All workplace tract keys reconcile with the historical TIGER geometry. Public
city-center checks in each state pass with geocoded-job coverage above 97%; these
checks are software QA, not model validation or protected-evidence coverage. The
predeclared 95% rule is applied uniformly without consulting targets. No additional
2020 LODES7 data is asserted: the retrieved 2021 guide ends at 2019.

### Census annual county residential permits

The [official county archive](https://www2.census.gov/econ/bps/County/) supplied the
2021, 2022 and 2023 annual files. The retained bytes have the following dates:

| Forecast year | Permit reference year | Last-modified date of preserved bytes | Official file |
| --- | --- | --- | --- |
| 2024 | 2021 | April 27, 2022 | [co2021a.txt](https://www2.census.gov/econ/bps/County/co2021a.txt) |
| 2025 | 2022 | April 25, 2024 | [co2022a.txt](https://www2.census.gov/econ/bps/County/co2022a.txt) |
| 2026 | 2023 | April 25, 2024 | [co2023a.txt](https://www2.census.gov/econ/bps/County/co2023a.txt) |

The fixed three-year lag avoids assuming the currently revised 2022 file was
available before 2024. A [separate June 2023 revision notice](https://www2.census.gov/econ/bps/County/co2022aupdatednotice.txt)
states that four omitted counties were added with no other changes; the adapter
nevertheless uses the dates of the exact retrieved bytes, not an inferred earlier
snapshot.

The two-line source header distinguishes total units from reported-only units for
1-unit, 2-unit, 3–4-unit and 5-or-more-unit structures. Two features use log total
permitted units and the share of units in multifamily structures. Census estimates
for survey nonresponse remain in the totals; the reported share is preserved as
quality information and never confused with the total. This describes authorization
to build, not completed housing, occupied households or neighborhood-specific
construction. These are coarse county signals.

Each reference year supplies all 83 Michigan and 72 Wisconsin actual counties.
Michigan also has a `000` balance-of-state row. That unallocated category is excluded
from county joins and is never distributed across locations. Missing counties or
unit fields stay missing. A recorded zero-unit county has zero permit count and an
undefined multifamily share. Duplicate county rows, reference-year mismatch,
header/total-versus-reported drift, and reported units exceeding totals fail closed.

### Sources investigated but not in these supplemental features

The following are bounded non-admissions, not evidence of statistical inferiority.
No rejected family is claimed to have undergone empirical ablation unless the final
execution report records that evaluation.

| Source | Verified evidence | Generation 1 disposition and limitation |
| --- | --- | --- |
| Newer LODES8 / separate employment-growth series | [Official data page](https://lehd.ces.census.gov/data/) and [archive](https://lehd.ces.census.gov/data/lodes/) identify 2020-block LODES8 versus 2010-block LODES7; LODES8 documentation has 2023, 2024 and 2025 versions | Archived LODES7 2019 main/aux OD and WAC are admitted below. Current LODES8 old-reference-year files are not silently backdated. A newer employment-growth series remains unmaterialized. |
| FHWA TMAS hourly traffic | [Official page](https://www.fhwa.dot.gov/policyinformation/tables/tmasdata/) lists station files and monthly traffic archives for 2010–2025 and a station map | Lawful historical archives exist. No qualified local station/road matching and comparable station-selection/coverage rule was materialized here. Road density is not a substitute claim for measured traffic. Hourly vehicle direction and AM/PM measures remain untested. |
| Wisconsin DOT AADT | [Official page](https://wisconsindot.gov/Pages/projects/data-plan/traf-counts/default.aspx) describes TCMap, historical counts, seasonal/axle adjustments, and short-duration collection on 3/6/10-year cycles at more than 26,000 sites | No cross-state equivalent frozen download/measurement contract was completed. A candidate Michigan documentation endpoint returned 404; that is not proof Michigan lacks public traffic data. Current map values are not backdated. |
| OSM historical POIs and roads | [Official wiki](https://wiki.openstreetmap.org/wiki/Planet.osm/full) documents full history, ODbL-redacted omissions, date extraction with Osmium, and regional history extracts; September 2026 full-history PBF is approximately 150.9 GB | Historical reconstruction is possible and was not rejected as unlawful. No historically frozen MI/WI category-completeness audit or bounded routing engine was built. Current POIs/roads are excluded from historical validation; grocery brands and co-tenancy remain an evidence gap. |
| Overture Places/buildings | [Official acquisition guide](https://docs.overturemaps.org/getting-data/) supports free no-account exploration, GeoJSON export, Python client and columnar queries; retrieved guide updated August 2026 | A guessed release-history endpoint returned 404. This investigation did not establish and materialize a release available before the earliest forecast cutoff, with stable category/coverage semantics. The current dataset is excluded from historical validation, not declared intrinsically inadmissible. |
| NLCD/Annual NLCD | [MRLC page](https://www.mrlc.gov/data) says the site currently exposes Annual NLCD Collection 1 Version 2 only and links a ScienceBase archive | No release-pinned historical raster was acquired and processed. Latest historical land-cover estimates can contain later reprocessing; no backdating. Remote-sensing family remains untested. |
| VIIRS nighttime lights | [EOG documentation](https://eogdata.mines.edu/products/vnl/) describes V2/V2.1/V2.2, the July 2023 V2.2 readme, 15-arc-second grids and cloud/stray-light treatment | The direct V2.2 version-directory request returned HTTP401. The guide warns that zero radiance with absent cloud-free observations cannot mean no lights and explains multiyear thresholding. No dated raster, quality mask or lawful reuse record was fully materialized; nightlights remain untested. |
| Later Building Permits Survey releases | [Official annual page](https://www.census.gov/construction/bps/annual.html) currently describes final 2025 permits released May 14, 2026 | The historical 2021/2022/2023 county series is admitted above. Current 2025 data are too late for earlier forecasts and are not substituted. |
| BEA/BLS growth, local permits/business licenses, stand-alone GTFS/building footprints | Considered as source families; no completed official-data acquisition/validation for these products in this implementation | Not empirically tested. Local harmonization, frozen release history and added effective complexity remain open. Do not claim exhaustive public-data coverage. |
| Paid mobile-location, proprietary raw commercial networks/data, direct protected characteristics, future store openings | Outside authorized admissibility boundary | Excluded. Public government statistical products with documented commercial upstream lineage are distinguished from acquiring proprietary raw products. No source was rejected solely because it was unconventional or politically sensitive. |

The defensible claim is a materially broader public-data comparison with explicit
coverage gaps. It is not that all free public information was exhausted or that an
unmaterialized family could not improve the model. Further empirical use after the
one-time holdout requires the user-authorized successor-generation process.
