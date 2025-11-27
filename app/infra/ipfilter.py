import ipaddress
import os
import re
import urllib.request


def _parse_allowlist(raw: str) -> list[ipaddress._BaseNetwork]:
	items = [x.strip() for x in raw.split(",") if x.strip()]
	cidrs: list[ipaddress._BaseNetwork] = []
	for item in items:
		try:
			# Accept single IP by converting to /32 or /128
			if "/" not in item:
				ip = ipaddress.ip_address(item)
				net = ipaddress.ip_network(f"{ip}/{ip.max_prefixlen}", strict=False)
			else:
				net = ipaddress.ip_network(item, strict=False)
			cidrs.append(net)
		except Exception:
			continue
	return cidrs


def get_ip_allowlist() -> list[ipaddress._BaseNetwork]:
	raw = os.environ.get("IP_ALLOWLIST", "").strip()
	if not raw:
		return []
	return _parse_allowlist(raw)

_cached_my_ip: str | None = None


def _resolve_my_public_ip() -> str | None:
	global _cached_my_ip
	if _cached_my_ip:
		return _cached_my_ip
	# 1) Explicit override
	env_ip = os.environ.get("MY_PUBLIC_IP", "").strip()
	if env_ip:
		try:
			ipaddress.ip_address(env_ip)
			_cached_my_ip = env_ip
			return _cached_my_ip
		except Exception:
			pass
	# 2) Try external service with short timeout
	for url in ("https://api.ipify.org", "https://ifconfig.me/ip"):
		try:
			req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
			with urllib.request.urlopen(req, timeout=2.0) as resp:
				body = resp.read().decode("utf-8").strip()
				body = body.split()[0]
				# basic sanity check
				if re.match(r"^[0-9a-fA-F\.:]+$", body):
					ipaddress.ip_address(body)
					_cached_my_ip = body
					return _cached_my_ip
		except Exception:
			continue
	return None


def get_effective_allowlist() -> list[ipaddress._BaseNetwork]:
	"""
	Merges static allowlist with current machine's public IP when AUTO_ALLOW_MY_IP=true.
	"""
	static = get_ip_allowlist()
	auto = (os.environ.get("AUTO_ALLOW_MY_IP", "false") or "false").lower() in {"1", "true", "yes"}
	if not auto:
		return static
	my_ip = _resolve_my_public_ip()
	if not my_ip:
		return static
	# Add my IP as /32 or /128
	try:
		ip = ipaddress.ip_address(my_ip)
		net = ipaddress.ip_network(f"{ip}/{ip.max_prefixlen}", strict=False)
		# Avoid duplicates
		if all(ip not in n for n in static):
			return static + [net]
	except Exception:
		pass
	return static


def is_ip_allowed(ip_str: str | None, allowlist: list[ipaddress._BaseNetwork]) -> bool:
	if not allowlist:
		# No allowlist configured → allow all
		return True
	if not ip_str:
		return False
	try:
		ip = ipaddress.ip_address(ip_str)
	except Exception:
		return False
	for net in allowlist:
		if ip in net:
			return True
	return False


