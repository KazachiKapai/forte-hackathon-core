import json
from typing import Dict, List, Optional
from ..config.logging_config import configure_logging
import time

try:
	from jira import JIRA  # type: ignore
except Exception:  # pragma: no cover
	JIRA = None  # type: ignore

_LOGGER = configure_logging()


class JiraService:
	def __init__(self, base_url: str, email: str, api_token: str, project_keys: Optional[List[str]] = None, max_issues: int = 5) -> None:
		if JIRA is None:
			raise RuntimeError("jira package is not installed; install `jira` to enable Jira integration")
		self.base_url = base_url.rstrip("/")
		self.email = email
		self.api_token = api_token
		self.project_keys = project_keys or []
		self.max_issues = max(1, max_issues)
		# Initialize official Jira client
		try:
			self.client = JIRA(server=self.base_url, basic_auth=(self.email, self.api_token), options={"rest_api_version": "3"})
		except Exception:
			_LOGGER.exception("Failed to initialize Jira client")
			raise

	def _post_json(self, path: str, body: Dict) -> Dict:
		url = f"{self.base_url}{path}"
		resp = self.client._session.post(url, data=json.dumps(body), headers={"Content-Type": "application/json", "Accept": "application/json"})
		if resp.status_code >= 400:
			raise RuntimeError(f"HTTP {resp.status_code} {resp.reason}: {resp.text}")
		return resp.json()

	def _get_json(self, path: str, params: Optional[Dict] = None) -> Dict:
		url = f"{self.base_url}{path}"
		resp = self.client._session.get(url, params=params, headers={"Accept": "application/json"})
		if resp.status_code >= 400:
			raise RuntimeError(f"HTTP {resp.status_code} {resp.reason}: {resp.text}")
		return resp.json()

	def search_related_issues(
		self,
		title: str,
		description: str,
		labels: List[str],
		created_at_iso: Optional[str],
		search_window: str = "-30d",
		mr_url: Optional[str] = None,
	) -> List[Dict[str, str]]:
		def _esc(s: str) -> str:
			return s.replace("\\", "\\\\").replace('"', '\\"')
		# Build multiple focused JQLs with OR-combined tokens to improve recall
		queries: List[Dict[str, str]] = []
		prefix = f'project in ({",".join(self.project_keys)})' if self.project_keys else ""
		# Tokenize title/description words and keep top N
		title_tokens = [w for w in (title or "").split() if len(w) >= 3][:6]
		desc_tokens = [w for w in (description or "").split() if len(w) >= 5][:6]
		if title_tokens:
			s_or = " OR ".join([f'summary ~ "{_esc(t)}"' for t in title_tokens])
			queries.append({"jql": f'{prefix + " AND " if prefix else ""}({s_or})'})
			d_or = " OR ".join([f'description ~ "{_esc(t)}"' for t in title_tokens])
			queries.append({"jql": f'{prefix + " AND " if prefix else ""}({d_or})'})
		if desc_tokens:
			d2_or = " OR ".join([f'description ~ "{_esc(t)}"' for t in desc_tokens])
			queries.append({"jql": f'{prefix + " AND " if prefix else ""}({d2_or})'})
		# Labels OR
		if labels:
			lbls = ",".join([f'"{_esc(l)}"' for l in labels[:5]])
			queries.append({"jql": f'{prefix + " AND " if prefix else ""}(labels in ({lbls}))'})
		# MR URL exact match in description (high precision)
		if mr_url:
			queries.append({"jql": f'{prefix + " AND " if prefix else ""}(description ~ "{_esc(mr_url)}")'})
		# Time-based narrowing: created_at_iso (as date-only) and updated >= search_window
		if created_at_iso:
			# Convert ISO to date-only to avoid time format issues in JQL
			date_only = created_at_iso.split("T")[0]
			queries.append({"jql": f'{prefix + " AND " if prefix else ""}created >= "{_esc(date_only)}"'})
		if search_window:
			queries.append({"jql": f'{prefix + " AND " if prefix else ""}updated >= {search_window}'})
		# Fallback generic
		if not queries:
			queries.append({"jql": prefix or "ORDER BY updated DESC"})
		_LOGGER.info("Jira search queries_count=%s maxResults=%s", len(queries), self.max_issues)
		all_issues: Dict[str, Dict] = {}
		for idx, q in enumerate(queries):
			jql = q.get("jql", "")
			if not jql:
				continue
			ok = False
			data = {}
			for attempt in range(2):
				try:
					# New API via official client's session: POST /rest/api/3/search/jql
					body_jql: Dict = {
						"jql": jql,
						"maxResults": self.max_issues,
						# Request fields explicitly; API may still return IDs only
						"fields": ["summary", "status", "updated"],
					}
					data = self._post_json("/rest/api/3/search/jql", body_jql)
					ok = True
					break
				except Exception as e:
					err_body = str(e)
					_LOGGER.error(f"Jira search/jql failed | attempt={attempt + 1} | jql={jql} | body={err_body}")
					if attempt == 0:
						time.sleep(3)
			if not ok:
				# fallback issue picker per query token set
				try:
					qtoken = jql.split('"')
					token = qtoken[1] if len(qtoken) > 1 else ""
					pk = self._get_json("/rest/api/3/issue/picker", params={"query": token})
					for it in (pk.get("issues") or []):
						key = it.get("key", "")
						if key and key not in all_issues:
							all_issues[key] = {"key": key, "fields": {"summary": it.get("summary", ""), "status": {"name": ""}, "updated": ""}}
					_LOGGER.info("Jira fallback issue picker used", extra={"token": token})
				except Exception:
					continue
			else:
				# Normalize and accumulate
				raw_issues = []
				if isinstance(data, dict):
					raw_issues = data.get("issues") or []
				# If fields are missing, bulk fetch minimal fields
				need_bulk = False
				for it in raw_issues:
					f = it.get("fields")
					if not isinstance(f, dict) or ("summary" not in f and "status" not in f and "updated" not in f):
						need_bulk = True
						break
				if need_bulk and raw_issues:
					try:
						ids_or_keys = []
						for it in raw_issues:
							key = it.get("key") or it.get("id")
							if key:
								ids_or_keys.append(key)
						bulk_body = {"issueIdsOrKeys": ids_or_keys, "fields": ["summary", "status", "updated"]}
						bulk = self._post_json("/rest/api/3/issue/bulkfetch", bulk_body)
						if isinstance(bulk, dict):
							# Bulk may return issues list or map; normalize to list
							bulk_items = []
							if "issues" in bulk and isinstance(bulk.get("issues"), list):
								bulk_items = bulk.get("issues") or []
							elif "results" in bulk and isinstance(bulk.get("results"), list):
								bulk_items = bulk.get("results") or []
							by_key: Dict[str, Dict] = {}
							for bi in bulk_items:
								k = bi.get("key") or bi.get("id")
								if k:
									by_key[k] = bi
							# merge fields back
							for it in raw_issues:
								k = it.get("key") or it.get("id")
								if k and k in by_key:
									if "fields" not in it or not isinstance(it.get("fields"), dict):
										it["fields"] = {}
									it["fields"].update(by_key[k].get("fields") or {})
					except Exception:
						_LOGGER.exception("Jira bulkfetch failed; proceeding with available fields")
				keys = []
				for it in raw_issues:
					key = it.get("key") or it.get("id")
					if key and key not in all_issues:
						all_issues[key] = it
						keys.append(key)
				_LOGGER.info("Jira query matched", extra={"jql": jql, "count": len(keys), "keys": keys[:5]})
			# Stop early if we have enough
			if len(all_issues) >= self.max_issues:
				break
		raw_list = list(all_issues.values())[: self.max_issues]
		issues_out: List[Dict[str, str]] = []
		for it in raw_list:
			key = it.get("key")
			fields = it.get("fields") or {}
			summary = fields.get("summary") or ""
			status = ((fields.get("status") or {}).get("name")) or ""
			updated = fields.get("updated") or ""
			issues_out.append(
				{
					"key": key,
					"summary": summary,
					"status": status,
					"updated": updated,
					"url": f"{self.base_url}/browse/{key}" if key else "",
				}
			)
		_LOGGER.info(
			"Jira search final",
			extra={"matched": len(issues_out), "keys": [i.get("key") for i in issues_out]},
		)
		return issues_out
	
	def add_remote_link(self, issue_key: str, url: str, title: Optional[str] = None) -> None:
		"""
		Create a remote link from Jira issue to an external resource (e.g., GitLab MR).
		"""
		if not issue_key or not url:
			return
		try:
			# jira client expects top-level url/title
			self.client.add_remote_link(issue_key, {"url": url, "title": title or url})
		except Exception:
			_LOGGER.exception("Jira add_remote_link failed")

	def create_issue(
		self,
		project_key: str,
		summary: str,
		description: str,
		labels: Optional[List[str]] = None,
		issue_type: str = "Task",
	) -> Optional[Dict[str, str]]:
		def _to_adf(text: str) -> Dict:
			paras = [p for p in (text or "").split("\n\n") if p.strip()]
			content = []
			for p in paras:
				# Preserve newlines within paragraph as hardBreaks
				segments = p.split("\n")
				inner = []
				for idx, seg in enumerate(segments):
					if seg:
						inner.append({"type": "text", "text": seg})
					if idx < len(segments) - 1:
						inner.append({"type": "hardBreak"})
				if not inner:
					inner = [{"type": "text", "text": ""}]
				content.append({"type": "paragraph", "content": inner})
			if not content:
				content = [{"type": "paragraph", "content": [{"type": "text", "text": ""}]}]
			return {"type": "doc", "version": 1, "content": content}
		desc_adf = _to_adf(description)
		_LOGGER.debug(
			"Jira create_issue request",
			extra={
				"project_key": project_key,
				"issue_type": issue_type,
				"summary_len": len(summary or ""),
				"labels_count": len(labels or []),
				"desc_nodes": len(desc_adf.get("content", [])),
			},
		)
		try:
			fields = {
				"project": {"key": project_key},
				"summary": summary[:254],
				"description": desc_adf,
				"issuetype": {"name": issue_type},
			}
			if labels:
				fields["labels"] = labels[:10]
			issue = self.client.create_issue(fields=fields)
		except Exception as e:
			_LOGGER.exception("Jira create_issue exception")
			raise
		key = getattr(issue, "key", None)
		if not key:
			return None
		return {"key": key, "url": f"{self.base_url}/browse/{key}"}

	def list_projects(self, max_results: int = 200) -> List[Dict[str, str]]:
		try:
			projects = self.client.projects()
		except Exception:
			_LOGGER.exception("Jira list_projects exception")
			return []
		out: List[Dict[str, str]] = []
		for prj in projects or []:
			try:
				out.append({"key": getattr(prj, "key", "") or "", "name": getattr(prj, "name", "") or ""})
			except Exception:
				continue
		return out


