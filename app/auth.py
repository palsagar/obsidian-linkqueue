import jwt
from fastapi import Request
from fastapi.responses import JSONResponse


def install_cloudflare_auth(app, team_domain: str, policy_aud: str) -> None:
    """Reject requests whose Cf-Access-Jwt-Assertion doesn't verify against
    Cloudflare Access certs for the team. Belt-and-suspenders behind Access."""
    certs_url = f"https://{team_domain}/cdn-cgi/access/certs"
    jwk_client = jwt.PyJWKClient(certs_url)

    @app.middleware("http")
    async def verify_cf_access(request: Request, call_next):
        token = request.headers.get("Cf-Access-Jwt-Assertion")
        if not token:
            return JSONResponse({"detail": "missing Cloudflare Access token"}, status_code=403)
        try:
            key = jwk_client.get_signing_key_from_jwt(token)
            jwt.decode(token, key.key, algorithms=["RS256"], audience=policy_aud)
        except jwt.PyJWTError:
            return JSONResponse({"detail": "invalid Cloudflare Access token"}, status_code=403)
        return await call_next(request)
