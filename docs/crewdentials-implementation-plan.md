# Crewdentials crew lookup implementation plan

Implementation update, 21 October 2026: the original lookup proposal below is
historical. The application now uses a local allowlist of connected development
profile IDs with the supplied `/v1/getCrewDocs/{crewProfileId}` contract, explicit
vessel assignments and provisional crew/combined assessment models. See the
README's **Crew evidence and combined vessel assessment** section for the current
workflow and scoring rules. No global name/email discovery is assumed.

Status: Draft for review  
Date: 16 October 2026

## Purpose

Allow an authorised MCI user to enter a crew member's name and email address, find an accessible Crewdentials record, review the available information and link the correct person to a vessel assessment.

The first release should establish reliable lookup and retrieval. Qualifications, CV interpretation and risk findings follow once the actual response fields and access permissions are confirmed.

## Developer documentation and integration assumptions

Source: [Crewdentials developer documentation](https://www.crewdentials.com/resources/developers), reviewed 16 October 2026.

The page documents these operations:

| Operation | Request |
| --- | --- |
| Search by email | `GET https://crewdentials.app/api/crew?email={email}` |
| Search by surname | `GET https://crewdentials.app/api/crew?lastName={surname}` |
| Retrieve a person | `GET https://crewdentials.app/api/crew/{crew_id}` |
| Create and invite a person | `POST https://crewdentials.app/api/crew` |

It specifies `Authorization: API {access_key_id} {secret_access_key}`. Search returns a `results` array; example records include `id`, `firstName`, `lastName` and `emails`.

Search is described as searching your crew list. The examples omit most record fields. Neither global discovery nor complete CV/certificate retrieval is established by this page. It also describes signed crew-update webhooks and an optional profile auto-sync setting. [Source](https://www.crewdentials.com/resources/developers)

James's email describes a separate development integration using `/insertCrewDocs`, `/getCrewDocs/:crewProfileId`, a workflow ID and a single development key. Do not assume those credentials or endpoints are interchangeable with the public API. The Postman collection and a representative response must settle that contract.

## Proposed user journey

1. Open the Crew tab on a vessel assessment.
2. Enter first name, surname, email and proposed role.
3. Select **Find crew member**.
4. Review candidate matches and any name discrepancy.
5. Select the correct candidate to retrieve their accessible record.
6. Review available qualifications, experience, verification evidence and missing information.
7. Confirm the person-to-vessel link, role and assignment dates.

Search by email first. Offer surname search as an explicit fallback. A failed lookup must not automatically create a profile, send an invitation or imply that the person has no qualifications.

| Outcome | Application behaviour |
| --- | --- |
| One candidate with a consistent name | Show the candidate for confirmation before linking |
| Name differs from the submitted name | Show the discrepancy and require review |
| Multiple candidates | Require selection; do not choose the first result |
| No accessible match | Show `No accessible crew record found` |
| Provider unavailable | Show a retryable service error, distinct from no match |
| Record lacks CV or certificates | Show explicit missing-information states |

Email matching is a record-matching aid, not independent identity verification. Name comparison should highlight discrepancies without rejecting legitimate variations automatically.

## Proposed application structure

The existing application uses FastAPI, Pydantic, Jinja templates and a repository abstraction. Add a separate crew domain:

| Proposed file | Responsibility |
| --- | --- |
| `app/crewdentials.py` | Provider client and response validation |
| `app/crew_models.py` | Lookup inputs, candidate summaries and evidence models |
| `app/crew_services.py` | Matching, retrieval, review and assessment orchestration |
| `app/crew_repositories.py` | Tenant-scoped person links and permitted evidence snapshots |
| `app/templates/crew.html` | Lookup, candidate review and evidence display |
| `tests/test_crewdentials.py` | Provider contract and error handling tests |
| `tests/test_crew_services.py` | Matching, authorisation and linking tests |

Suggested internal routes:

| Route | Purpose |
| --- | --- |
| `POST /api/crew/lookup` | Search with personal information in the request body |
| `POST /api/crew/retrieve` | Retrieve a selected, server-recorded candidate |
| `POST /api/vessels/{vessel_id}/crew` | Confirm an authorised vessel assignment |
| `POST /api/crew/{person_id}/refresh` | Refresh an already linked person's evidence |

Apply the application's authentication, role, tenant and CSRF controls before exposing these routes. A provider ID received from the browser must be checked against server-recorded candidates for the user's tenant and lookup session. It must not grant arbitrary access to another person's record.

## Reference configuration

These are proposed settings, not credentials. Confirm the development base URL and authentication before running the examples.

```dotenv
CREWDENTIALS_ENABLED=false
CREWDENTIALS_BASE_URL=https://crewdentials.app/api/
CREWDENTIALS_ACCESS_KEY_ID=
CREWDENTIALS_SECRET_ACCESS_KEY=
CREWDENTIALS_TIMEOUT_SECONDS=15
```

Use environment variables locally and Key Vault in Azure. Keep real values out of source control, browser code and logs. Restrict the configured destination to the approved HTTPS provider host.

The reference client uses `httpx`, which is currently a development dependency in this project. Move it into runtime dependencies when implementing the feature.

## Reference Python client

This is review code for the publicly documented authentication and response shape. It is not yet wired into the application. Unknown provider fields are retained by the client temporarily so the service can map an approved subset after the schema is confirmed.

```python
from typing import Any
from urllib.parse import quote

import httpx


class CrewdentialsUnavailable(RuntimeError):
    """Provider failure; do not present this as an empty search."""


class CrewdentialsContractError(RuntimeError):
    """The response does not match the agreed integration contract."""


class CrewdentialsClient:
    def __init__(self, http: httpx.AsyncClient):
        # The caller owns the client and closes it at application shutdown.
        self.http = http

    async def _get(self, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = await self.http.get(path, **kwargs)
            response.raise_for_status()
        except httpx.HTTPError:
            # Do not expose exception URLs, headers or response bodies to users.
            # Provider search URLs contain email addresses.
            raise CrewdentialsUnavailable("Crew lookup is unavailable") from None

        try:
            payload = response.json()
        except ValueError:
            raise CrewdentialsContractError("Invalid provider JSON") from None
        if not isinstance(payload, dict):
            raise CrewdentialsContractError("Expected a JSON object")
        return payload

    async def search_by_email(self, email: str) -> list[dict[str, Any]]:
        payload = await self._get("crew", params={"email": email.strip()})
        results = payload.get("results")
        if not isinstance(results, list):
            raise CrewdentialsContractError("Expected a results array")
        for record in results:
            if not isinstance(record, dict):
                raise CrewdentialsContractError("Invalid candidate record")
            if not isinstance(record.get("id"), str) or not record["id"]:
                raise CrewdentialsContractError("Candidate has no valid ID")
        return results

    async def get_crew(self, crew_id: str) -> dict[str, Any]:
        if not crew_id.strip():
            raise ValueError("A crew ID is required")
        record = await self._get(f"crew/{quote(crew_id, safe='')}")
        if record.get("id") != crew_id:
            raise CrewdentialsContractError("Unexpected crew record ID")
        return record
```

Construct the shared HTTP client during application startup and close it during shutdown:

```python
# Values come from validated server settings. This base URL must end in '/'.
http = httpx.AsyncClient(
    base_url=settings.crewdentials_base_url,
    headers={
        "Authorization": (
            f"API {settings.crewdentials_access_key_id} "
            f"{settings.crewdentials_secret_access_key}"
        ),
        "Accept": "application/json",
    },
    timeout=httpx.Timeout(settings.crewdentials_timeout_seconds),
    follow_redirects=False,
)
provider = CrewdentialsClient(http)

# At shutdown:
# await http.aclose()
```

Before production use, add bounded retries for transient failures, respect rate-limit responses, enforce response-size limits and ensure HTTP/access logging redacts provider query parameters. Do not retry authentication or contract failures blindly.

## Reference lookup service

This example deliberately returns candidate summaries for review. Full records remain server-side until an authorised user selects a candidate. The API response fields below are MCI's proposed contract, not Crewdentials fields.

```python
import unicodedata
from typing import Any


def normalise_name(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


async def lookup_candidates(
    provider: CrewdentialsClient,
    first_name: str,
    last_name: str,
    email: str,
) -> dict[str, Any]:
    records = await provider.search_by_email(email)
    candidates = []
    for record in records:
        first = record.get("firstName")
        last = record.get("lastName")
        if not isinstance(first, str) or not isinstance(last, str):
            raise CrewdentialsContractError("Missing candidate name fields")

        emails = record.get("emails")
        if not isinstance(emails, list) or any(
            not isinstance(value, str) for value in emails
        ):
            raise CrewdentialsContractError("Unexpected candidate email fields")

        # Conservative matching aid; email normalisation policy must be agreed.
        email_consistent = any(
            value.strip().casefold() == email.strip().casefold()
            for value in emails
        )
        name_consistent = (
            normalise_name(first) == normalise_name(first_name)
            and normalise_name(last) == normalise_name(last_name)
        )
        candidates.append({
            "crewId": record["id"],
            "firstName": first,
            "lastName": last,
            "nameConsistent": name_consistent,
            "emailConsistent": email_consistent,
        })

    return {
        "status": "REVIEW_REQUIRED" if candidates else "NOT_FOUND",
        "candidates": candidates,
    }
```

The route must validate input lengths and email syntax, authorise the user and vessel context, and save the candidate IDs against a short-lived tenant/user-scoped lookup reference. On selection, validate that reference before calling `get_crew`. Escape provider text in templates and never render it as trusted HTML.

The service does not assume that supplying both email and surname as provider query parameters is supported. Pagination and search completeness also need confirmation before relying on candidate counts.

## Information model and document boundary

Keep these concepts separate:

| Concept | Minimum proposed information |
| --- | --- |
| MCI person | Internal ID, tenant, reviewed identity and provider crew ID |
| Provider profile | Profile ID, environment/workspace and workflow where applicable |
| Vessel assignment | Person ID, vessel ID, role, effective dates and reviewer |
| Evidence | Type, permitted structured facts, source/profile/document IDs and verification status |
| Retrieval | Provider, retrieval time, source version if available and freshness |
| Assessment | Requirements version, evidence versions, findings and reviewer decision |

Return and store only the fields authorised for this purpose. Do not expose or persist arbitrary full provider payloads by default. Missing fields must remain unknown rather than receiving favourable defaults.

Preserve the existing architecture: Document Intake owns crew attachment storage and controlled document access. CAT retains permitted metadata and opaque references. Do not download CVs or certificates into CAT storage as a side effect of lookup.

An existing `crewId` may relate to multiple profiles, according to James's email. Never assume a one-to-one crew/profile relationship or select the first profile without a defined policy.

## Risk assessment after retrieval

Once the data contract is confirmed, map the permitted evidence to a reviewed requirements matrix for the person's role, vessel characteristics, flag, operating area and assignment dates.

Initial findings can include:

- Required qualification missing, expired or awaiting verification.
- Recorded qualification limits inconsistent with the proposed assignment.
- Qualification expiry during the assignment period.
- Relevant experience evidenced, self-declared or unknown.
- Conflicting CV dates requiring review.

Keep evidence confidence separate from suitability findings. Extracted text does not establish certificate authenticity; an email match does not verify identity. The first release should produce explainable review prompts rather than an uncalibrated numerical crew score or automatic underwriting decision.

## Delivery phases and acceptance checks

| Phase | Work | Acceptance check |
| --- | --- | --- |
| 1. Confirm API contract | Obtain environment/auth details, sample responses and access scope | A known development person can be searched and retrieved through the agreed API |
| 2. Implement client | Settings, HTTP lifecycle, validation and error handling | Mocked tests cover success, empty results, malformed responses, auth failure, timeout and rate limiting |
| 3. Build lookup workflow | Form, candidate review and authorised retrieval | Multiple matches and name discrepancies cannot silently select or link a person |
| 4. Persist reviewed links | Tenant-scoped person and assignment records | Cross-tenant access is rejected; repeated linking does not create duplicates |
| 5. Display evidence | Map confirmed fields, source references and gaps | Missing CV/certificate data is visibly distinguished from verified evidence |
| 6. Add assessment | Versioned requirements and explainable findings | Expiry and role-limit scenarios produce traceable findings |
| 7. Add updates | Manual refresh, then agreed provider events | Failed refresh preserves the previous evidence with a stale/error state |

The immediate milestone is phases 1–3: enter a known test person's name and email, select the correct candidate and display the permitted returned record. No invitations, uploads or webhook registration are needed for that milestone.

## Questions for James

1. Does MCI search only its workspace crew list, connected profiles or a broader directory? What sharing or connection step is needed for a new person?
2. What development base URL and authentication apply to the public lookup endpoints? Does the supplied single key support them?
3. Can you supply complete, redacted search/detail responses or an OpenAPI schema, including nullable fields, errors and pagination?
4. Which response fields contain qualifications, experience, CV references, certificate references and verification outcomes?
5. How do we obtain and select `crewProfileId` from a `crewId`? Can multiple profiles contain different accessible evidence?
6. Is `/getCrewDocs/:crewProfileId` required to retrieve existing evidence? What access and download rules apply?
7. What are the search semantics, rate limits, timeouts and expected update delays?
8. What does each verification status establish, and is source/authority evidence available?
9. Which update event should MCI use for profile changes versus verification completion, and what signing/replay/retry contract applies?
10. What retention, deletion and onward-use permissions apply to the data returned to MCI?

## Review status

This document contains a proposed implementation and reference code only. It does not change application behaviour, configure credentials, query crew records, create invitations or register webhooks. The examples require validation against the agreed MCI development API before implementation.
