# Project Charter

## Business problem

GBT needs a defensible view of where likely Sprouts-oriented households concentrate within a market before individual properties are pursued. The capability should help compare demographic fit, target-household mass, continuity or fragmentation, seed surroundings, directional displacement, and relevant market context without presenting a public-data proxy as proprietary truth.

## Intended users and decisions supported

The intended users are GBT analysts and decision-makers evaluating where site-sourcing effort should be concentrated. The product is intended to support:

- identifying strong customer-fit pockets and their household mass;
- understanding whether pockets are continuous or fragmented;
- examining customer geography around a Sprouts-provided seed point;
- testing whether movement from a seed improves or weakens modeled capture;
- comparing candidate context and defending displacement toward stronger concentrations; and
- prioritizing market areas for further human-led sourcing and diligence.

## In-scope MVP

Subject to later task-specific authorization, the MVP may include a reproducible public-data analytical layer, market-configured Milwaukee analysis, stable presentation outputs, and a locally functional Power BI presentation. Each capability requires separate source, variable, model, spatial, and acceptance decisions.

## Out of scope

The product is not Sprouts' proprietary customer model, an exact Esri Tapestry recreation, a final site-selection engine, a substitute for judgment, or an extension of the existing Sprouts Site Scanner. GOV-01 does not authorize ingestion, downloaded datasets, scoring, GIS calculations, a functioning report, proprietary integrations, cloud resources, APIs, databases, deployment pipelines, or organizational integrations.

## Accepted starting decisions

- Milwaukee is the first intended pilot.
- Markets expand through configuration, not copied code or repositories.
- Reproducible analytical and spatial work belongs upstream of presentation.
- Power BI is the intended, replaceable MVP presentation environment.
- Public-source candidates require legal, technical, coverage, freshness, reproducibility, and licensing validation before acceptance.
- Future proprietary sources must be able to augment or replace public adapters without being designed during GOV-01.

These are starting boundaries, not final production technology selections.

## Success criteria

A future accepted MVP should be reproducible, explainable, quality-flagged, market-configurable, reconstructable from source-controlled definitions, and useful for human decision support. It must disclose uncertainty, provenance, licensing assumptions, and model limitations; it must not depend silently on enterprise services or confidential committed inputs.

## Confidentiality classification

Repository documentation and synthetic fixtures may be shareable, but live seeds, pursuits, contacts, internal direction, credentials, proprietary inputs, confidential exports, and revealing screenshots are protected and must remain outside Git unless specifically reviewed and authorized.

## Future expansion boundary

Later markets and approved proprietary sources should use configuration and adapters around stable analytical and presentation contracts. Separate applications, cloned repositories, and vendor-specific coupling are outside the intended boundary.
