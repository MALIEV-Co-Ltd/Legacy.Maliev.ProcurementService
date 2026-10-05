# Procurement authenticated IAM source composition

Procurement's actual Program registers the existing Defaults workload exchange,
the scoped concrete IamServiceClient and its authenticated named IAM transport.
The source composition adapts accepted Country01113637c751c7bea1354517be7f8b56a1637bb9
origin and response-budget controls with accepted Defaults7edcd961024868513fd5f373cab3dcb261197f77.
The existing permission requirements and signed-claim fallback rules are unchanged.
Employee forced-live writes never gain a signed-claim fallback.

ServiceAuthentication:ClientId/ClientSecret are runtime configuration, with the
Auth login intersection of a nonblank trimmed identifier up to128 characters and
a nonblank secret of16..1024 characters. No client enrollment, secret, hash or
permission grant is supplied by this change. The unauthenticated camel-case
POST/auth/v1/service/login exchange needs an explicitly configured concrete Auth
origin in Services:Auth:BaseUrl (or Services:Auth). Production requires a canonical
HTTPS origin without credentials, path, query, fragment or whitespace.

The Auth response read is bounded to32KiB and10 seconds, including the shared
provider's body read. The registered clients disable automatic redirects and
redact Authorization and the IAM live-check credential. Service discovery and
the existing safe retry policy remain; unsafe service-login/IAM POST requests
are not automatically retried.

IAM checks use a separate workload Bearer obtained through that exchange. The
incoming employee subject remains principalId in the permission request, together
with permissionId, resourcePath and bypassCache:true for live checks.
IAM:LivePermissionChecks:Credential supplies the separate live-check header;
absence denies before transport. The shared IAM logical routing convention is
retained when no explicit IAM origin is supplied. It proves no reachable bridge.

The21 new runtime regression executions use actual Program/JWT/permission/client
registrations and PostgreSQL databases. Controlled remote Auth and IAM HTTP
authorities issue and validate synthetic RS256 workload tokens. They cover fresh
allow-to-deny changes, exact resource paths, missing enrollment/configuration,
unknown client, wrong secret, URI refusal, missing live key,401/503/malformed and
oversized responses, bounded stalled body reads, redirect refusal and expired
employee JWT. No IIamServiceClient or authorization handler is replaced.

These candidate controls require actual hosted execution. They do not constitute
a real AuthService Program exchange, production IAM bridge, production enrollment
or grant proof. Those external dependencies remain explicit. No deployment,
provider activation, persistent database write or source-baseline closure applies.
