"""
╔══════════════════════════════════════════════════════════════╗
║  ELASTIC INDEX — Elasticsearch Backend para el Oráculo       ║
║  Full-text search · Filtros combinados · Aggregations        ║
║  Fallback graceful a índice en memoria                       ║
╚══════════════════════════════════════════════════════════════╝
"""
import os
import json
import logging
import time
from datetime import datetime
from typing import Optional, List, Dict, Any

logger = logging.getLogger("ElasticIndex")

# ─── ES Index Schema ─────────────────────────────────────────

INDEX_NAME = "oraculo_intelligence"
INDEX_SETTINGS = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "refresh_interval": "5s",
        "analysis": {
            "analyzer": {
                "email_analyzer": {
                    "type": "pattern",
                    "pattern": "[@.\\s]+",
                    "lowercase": True,
                },
                "password_analyzer": {
                    "type": "pattern",
                    "pattern": "[^a-zA-Z0-9!@#$%&*]+",
                }
            }
        }
    },
    "mappings": {
        "dynamic": "strict",
        "properties": {
            # ─── Identifiers ───
            "id":               {"type": "keyword"},
            "keyword":          {"type": "keyword"},
            
            # ─── Full-text search fields ───
            "email":            {"type": "text", "analyzer": "email_analyzer", "fields": {"raw": {"type": "keyword"}}},
            "username":         {"type": "text", "analyzer": "standard"},
            "domain":           {"type": "text", "analyzer": "standard", "fields": {"raw": {"type": "keyword"}}},
            "content_preview":  {"type": "text", "analyzer": "standard"},
            "password":         {"type": "text", "analyzer": "password_analyzer"},
            "ip_address":       {"type": "ip"},
            "port":             {"type": "keyword"},
            "hash_value":       {"type": "keyword"},
            "hash_type":        {"type": "keyword"},
            
            # ─── Categorical filters ───
            "record_type":      {"type": "keyword"},
            "severity":         {"type": "keyword"},
            "source_type":      {"type": "keyword", "fields": {"text": {"type": "text"}}},
            "source_url":       {"type": "keyword"},
            
            # ─── Dates ───
            "discovered_at":    {"type": "date"},
            "discovered_date":  {"type": "date", "format": "yyyy-MM-dd"},
            
            # ─── Extra ───
            "extra_data":       {"type": "flattened"},
        }
    }
}

# ─── ES Query Builder ────────────────────────────────────────

def build_search_query(
    query_text: str = "",
    record_type: Optional[str] = None,
    severity: Optional[str] = None,
    source_type: Optional[str] = None,
    domain: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    keyword: Optional[str] = None,
    sort_by: str = "discovered_at",
    sort_order: str = "desc",
    from_: int = 0,
    size: int = 50,
) -> dict:
    """
    Build an Elasticsearch bool query combining full-text search + filters.
    
    Returns an ES query body dict ready for es.search(body=...).
    """
    must_clauses = []
    filter_clauses = []
    
    # ─── Full-text search across multiple fields ───
    if query_text:
        must_clauses.append({
            "multi_match": {
                "query": query_text,
                "fields": [
                    "email^3",
                    "domain^2",
                    "content_preview",
                    "username",
                    "password",
                    "source_url",
                ],
                "type": "best_fields",
                "fuzziness": "AUTO",
            }
        })
    
    # ─── Keyword filter ───
    if keyword:
        must_clauses.append({"term": {"keyword": keyword.lower()}})
    
    # ─── Filters ───
    if record_type:
        filter_clauses.append({"term": {"record_type": record_type}})
    if severity:
        filter_clauses.append({"term": {"severity": severity}})
    if source_type:
        filter_clauses.append({"term": {"source_type": source_type}})
    if domain:
        filter_clauses.append({"term": {"domain.raw": domain.lower()}})
    
    # ─── Date range filter ───
    if date_from or date_to:
        date_range = {}
        if date_from:
            date_range["gte"] = date_from
        if date_to:
            date_range["lte"] = date_to
        filter_clauses.append({"range": {"discovered_date": date_range}})
    
    # Build query
    query = {"bool": {}}
    if must_clauses:
        query["bool"]["must"] = must_clauses
    if filter_clauses:
        query["bool"]["filter"] = filter_clauses
    if not must_clauses and not filter_clauses:
        query = {"match_all": {}}
    
    return {
        "query": query,
        "sort": [{sort_by: {"order": sort_order}}],
        "from": from_,
        "size": size,
    }


def build_stats_aggregations() -> dict:
    """Build ES aggregations for statistics."""
    return {
        "aggs": {
            "by_record_type": {
                "terms": {"field": "record_type", "size": 20}
            },
            "by_severity": {
                "terms": {"field": "severity", "size": 10}
            },
            "by_domain": {
                "terms": {"field": "domain.raw", "size": 20}
            },
            "by_source": {
                "terms": {"field": "source_type", "size": 20}
            },
            "by_year": {
                "date_histogram": {
                    "field": "discovered_date",
                    "calendar_interval": "year",
                    "format": "yyyy",
                }
            },
            "critical_count": {
                "filter": {"term": {"severity": "critical"}}
            },
        }
    }


# ─── Memory Fallback Index ───────────────────────────────────

class MemoryIndex:
    """
    In-memory index (same interface as ElasticsearchIndex).
    Used as fallback when ES is not available.
    """
    
    def __init__(self):
        self.records: List[dict] = []
        self.search_history: List[dict] = []
        self._id_counter = 0
    
    def _next_id(self) -> str:
        self._id_counter += 1
        return f"mem_{int(time.time())}_{self._id_counter}"
    
    @property
    def available(self) -> bool:
        return True
    
    def index_record(self, record: dict) -> bool:
        """Index a single record."""
        if "id" not in record or not record["id"]:
            record["id"] = self._next_id()
        self.records.append(record.copy())
        return True
    
    def index_bulk(self, records: List[dict]) -> int:
        """Index multiple records. Returns count indexed."""
        count = 0
        for rec in records:
            if self.index_record(rec):
                count += 1
        return count
    
    def search(self, query_text: str = "", **filters) -> dict:
        """
        Search records with filtering (in-memory equivalent of ES search).
        Returns same format as ElasticsearchIndex.search()
        """
        results = list(self.records)
        
        # Apply filters
        if query_text:
            ql = query_text.lower()
            results = [
                r for r in results
                if ql in (r.get("email", "") or "").lower()
                or ql in (r.get("domain", "") or "").lower()
                or ql in (r.get("content_preview", "") or "").lower()
                or ql in (r.get("username", "") or "").lower()
            ]
        
        if filters.get("keyword"):
            kw = filters["keyword"].lower()
            results = [r for r in results if (r.get("keyword") or "").lower() == kw]
        
        if filters.get("record_type"):
            results = [r for r in results if r.get("record_type") == filters["record_type"]]
        
        if filters.get("severity"):
            results = [r for r in results if r.get("severity") == filters["severity"]]
        
        if filters.get("source_type"):
            results = [r for r in results if r.get("source_type") == filters["source_type"]]
        
        if filters.get("domain"):
            results = [r for r in results if filters["domain"].lower() in (r.get("domain") or "").lower()]
        
        if filters.get("date_from") or filters.get("date_to"):
            df = filters.get("date_from", "1900-01-01")
            dt = filters.get("date_to", "2100-01-01")
            results = [
                r for r in results
                if df <= (r.get("discovered_date") or "1900-01-01") <= dt
            ]
        
        # Sort by discovered_at desc
        results.sort(key=lambda r: r.get("discovered_at", ""), reverse=True)
        
        total = len(results)
        from_ = filters.get("from_", 0)
        size = filters.get("size", 50)
        paginated = results[from_:from_ + size]
        
        # Stats
        stats = self._compute_stats(results)
        
        return {
            "total": total,
            "results": paginated,
            "stats": stats,
            "took_ms": 0,
            "using_elasticsearch": False,
        }
    
    def _compute_stats(self, records: List[dict]) -> dict:
        stats = {
            "total": len(records),
            "by_type": {},
            "by_severity": {},
            "by_domain": {},
            "by_source": {},
        }
        for r in records:
            rt = r.get("record_type", "unknown")
            stats["by_type"][rt] = stats["by_type"].get(rt, 0) + 1
            
            sev = r.get("severity", "unknown")
            stats["by_severity"][sev] = stats["by_severity"].get(sev, 0) + 1
            
            dom = r.get("domain", "")
            if dom:
                stats["by_domain"][dom] = stats["by_domain"].get(dom, 0) + 1
            
            src = r.get("source_type", "unknown")
            stats["by_source"][src] = stats["by_source"].get(src, 0) + 1
        
        return stats
    
    def get_stats(self) -> dict:
        """Get overall index statistics."""
        stats = self._compute_stats(self.records)
        stats["search_history"] = self.search_history[-50:]
        stats["memory_index"] = True
        return stats
    
    def delete_all(self) -> int:
        """Delete all records. Returns count."""
        count = len(self.records)
        self.records = []
        return count
    
    def add_history(self, entry: dict):
        self.search_history.append(entry)


# ─── Elasticsearch Index ─────────────────────────────────────

class ElasticsearchIndex:
    """
    Elasticsearch-powered index for the Oracle Intelligence system.
    
    Features:
    - Full-text search across email, domain, content_preview, username
    - Filter by record_type, severity, source_type, domain, date range
    - Aggregations for statistics
    - Graceful fallback to MemoryIndex if ES is unavailable
    
    Configured via env vars:
    - ES_HOSTS: comma-separated list (default: http://localhost:9200)
    - ES_API_KEY: API key for Elastic Cloud
    - ES_USER / ES_PASSWORD: basic auth
    - ES_USE_SSL: true/false
    """
    
    def __init__(self):
        self._es = None
        self._fallback = MemoryIndex()
        self._index_name = INDEX_NAME
        self._initialized = False
        
        # Read config from env
        hosts_env = os.environ.get("ES_HOSTS", "http://localhost:9200")
        self.hosts = [h.strip() for h in hosts_env.split(",") if h.strip()]
        self.api_key = os.environ.get("ES_API_KEY", "")
        self.user = os.environ.get("ES_USER", "")
        self.password = os.environ.get("ES_PASSWORD", "")
        self.use_ssl = os.environ.get("ES_USE_SSL", "").lower() in ("true", "1", "yes")
        
        # Try to connect
        self._connect()
    
    def _connect(self):
        """Attempt to connect to Elasticsearch and create the index."""
        try:
            from elasticsearch import Elasticsearch
            from elasticsearch.exceptions import ConnectionError as ESConnectionError
            
            # Build client
            if self.api_key:
                self._es = Elasticsearch(
                    self.hosts,
                    api_key=self.api_key,
                    request_timeout=10,
                    retry_on_timeout=True,
                    max_retries=2,
                )
            elif self.user and self.password:
                self._es = Elasticsearch(
                    self.hosts,
                    basic_auth=(self.user, self.password),
                    request_timeout=10,
                    retry_on_timeout=True,
                    max_retries=2,
                )
            else:
                self._es = Elasticsearch(
                    self.hosts,
                    request_timeout=10,
                    retry_on_timeout=True,
                    max_retries=2,
                )
            
            # Test connection
            info = self._es.info()
            version = info.get("version", {}).get("number", "unknown")
            logger.info(f"✅ Elasticsearch connected — v{version} at {self.hosts}")
            
            # Create index if it doesn't exist
            if not self._es.indices.exists(index=self._index_name):
                self._es.indices.create(
                    index=self._index_name,
                    body=INDEX_SETTINGS,
                )
                logger.info(f"📦 Created index '{self._index_name}' with mappings")
            else:
                logger.info(f"📦 Using existing index '{self._index_name}'")
            
            self._initialized = True
            
        except ImportError:
            logger.warning("⚠️ elasticsearch-py not installed — using in-memory fallback")
            self._es = None
        except ESConnectionError as e:
            logger.warning(f"⚠️ Elasticsearch connection failed — using in-memory fallback: {e}")
            self._es = None
        except Exception as e:
            logger.warning(f"⚠️ Elasticsearch init error — using in-memory fallback: {e}")
            self._es = None
    
    @property
    def available(self) -> bool:
        """Check if ES is available and initialized."""
        return self._es is not None and self._initialized
    
    # ─── Indexing ──────────────────────────────────────────
    
    def index_record(self, record: dict) -> bool:
        """Index a single intelligence record."""
        if self.available:
            try:
                doc = self._prepare_doc(record)
                resp = self._es.index(
                    index=self._index_name,
                    id=doc.get("id"),
                    document=doc,
                    refresh="wait_for",
                )
                return resp.get("result") in ("created", "updated")
            except Exception as e:
                logger.error(f"ES index error: {e}")
                return self._fallback.index_record(record)
        else:
            return self._fallback.index_record(record)
    
    def index_bulk(self, records: List[dict]) -> int:
        """Index multiple records using bulk API. Returns count indexed."""
        if not records:
            return 0
        
        if self.available:
            try:
                from elasticsearch.helpers import bulk
                
                actions = []
                for rec in records:
                    doc = self._prepare_doc(rec)
                    actions.append({
                        "_index": self._index_name,
                        "_id": doc.get("id"),
                        "_source": doc,
                    })
                
                success, errors = bulk(
                    self._es,
                    actions,
                    chunk_size=100,
                    refresh=True,
                    raise_on_error=False,
                )
                if errors:
                    logger.warning(f"ES bulk indexing: {len(errors)} errors out of {len(actions)}")
                return success
            except Exception as e:
                logger.error(f"ES bulk index error: {e}")
                return self._fallback.index_bulk(records)
        else:
            return self._fallback.index_bulk(records)
    
    def _prepare_doc(self, record: dict) -> dict:
        """Prepare a record dict for ES indexing (ensure correct field types)."""
        doc = dict(record)
        
        # Ensure dates are in correct format
        if doc.get("discovered_at"):
            try:
                datetime.fromisoformat(str(doc["discovered_at"]))
            except (ValueError, TypeError):
                doc["discovered_at"] = datetime.now().isoformat()
        
        if doc.get("discovered_date"):
            try:
                datetime.strptime(str(doc["discovered_date"]), "%Y-%m-%d")
            except (ValueError, TypeError):
                doc["discovered_date"] = datetime.now().strftime("%Y-%m-%d")
        else:
            doc["discovered_date"] = datetime.now().strftime("%Y-%m-%d")
        
        # Ensure IP is valid
        if doc.get("ip_address"):
            import re
            ip = doc["ip_address"]
            if not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', str(ip)):
                doc["ip_address"] = None
        
        # Ensure integer fields
        for int_field in ["port"]:
            if doc.get(int_field) is not None:
                try:
                    doc[int_field] = int(doc[int_field])
                except (ValueError, TypeError):
                    doc[int_field] = None
        
        return doc
    
    # ─── Search ────────────────────────────────────────────
    
    def search(
        self,
        query_text: str = "",
        keyword: Optional[str] = None,
        record_type: Optional[str] = None,
        severity: Optional[str] = None,
        source_type: Optional[str] = None,
        domain: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        from_: int = 0,
        size: int = 50,
        include_stats: bool = True,
    ) -> dict:
        """
        Search across indexed records with full-text + filters.
        
        Returns: {
            "total": int,
            "results": [dict],
            "stats": { by_type, by_severity, by_domain, by_source },
            "took_ms": int,
            "using_elasticsearch": bool,
        }
        """
        start = time.time()
        
        if self.available:
            try:
                # Build query
                body = build_search_query(
                    query_text=query_text,
                    keyword=keyword,
                    record_type=record_type,
                    severity=severity,
                    source_type=source_type,
                    domain=domain,
                    date_from=date_from,
                    date_to=date_to,
                    from_=from_,
                    size=size,
                )
                
                # Add aggregations if stats requested
                if include_stats:
                    body.update(build_stats_aggregations())
                
                # Execute search
                resp = self._es.search(
                    index=self._index_name,
                    body=body,
                )
                
                took = int((time.time() - start) * 1000)
                
                # Parse hits
                hits = resp.get("hits", {})
                total = hits.get("total", {}).get("value", 0)
                results = [h["_source"] for h in hits.get("hits", [])]
                
                # Parse aggregations
                stats = None
                if include_stats and "aggregations" in resp:
                    aggs = resp["aggregations"]
                    stats = {
                        "by_type": {b["key"]: b["doc_count"] for b in aggs.get("by_record_type", {}).get("buckets", [])},
                        "by_severity": {b["key"]: b["doc_count"] for b in aggs.get("by_severity", {}).get("buckets", [])},
                        "by_domain": {b["key"]: b["doc_count"] for b in aggs.get("by_domain", {}).get("buckets", [])},
                        "by_source": {b["key"]: b["doc_count"] for b in aggs.get("by_source", {}).get("buckets", [])},
                        "by_year": {b["key_as_string"]: b["doc_count"] for b in aggs.get("by_year", {}).get("buckets", [])},
                        "total": total,
                    }
                
                return {
                    "total": total,
                    "results": results,
                    "stats": stats,
                    "took_ms": took,
                    "using_elasticsearch": True,
                }
                
            except Exception as e:
                logger.error(f"ES search error: {e}")
                # Fallback
                return self._fallback.search(query_text=query_text, **{
                    "keyword": keyword,
                    "record_type": record_type,
                    "severity": severity,
                    "source_type": source_type,
                    "domain": domain,
                    "date_from": date_from,
                    "date_to": date_to,
                    "from_": from_,
                    "size": size,
                })
        else:
            return self._fallback.search(query_text=query_text, **{
                "keyword": keyword,
                "record_type": record_type,
                "severity": severity,
                "source_type": source_type,
                "domain": domain,
                "date_from": date_from,
                "date_to": date_to,
                "from_": from_,
                "size": size,
            })
    
    # ─── Stats ─────────────────────────────────────────────
    
    def get_stats(self) -> dict:
        """Get overall index statistics with aggregations."""
        if self.available:
            try:
                body = {
                    "query": {"match_all": {}},
                    "size": 0,
                    **build_stats_aggregations(),
                }
                resp = self._es.search(index=self._index_name, body=body)
                aggs = resp.get("aggregations", {})
                
                total = resp.get("hits", {}).get("total", {}).get("value", 0)
                
                stats = {
                    "total_records": total,
                    "by_type": {b["key"]: b["doc_count"] for b in aggs.get("by_record_type", {}).get("buckets", [])},
                    "by_severity": {b["key"]: b["doc_count"] for b in aggs.get("by_severity", {}).get("buckets", [])},
                    "by_domain": {b["key"]: b["doc_count"] for b in aggs.get("by_domain", {}).get("buckets", [])},
                    "by_source": {b["key"]: b["doc_count"] for b in aggs.get("by_source", {}).get("buckets", [])},
                    "by_year": {b["key_as_string"]: b["doc_count"] for b in aggs.get("by_year", {}).get("buckets", [])},
                    "critical_count": aggs.get("critical_count", {}).get("doc_count", 0),
                    "using_elasticsearch": True,
                    "index_name": self._index_name,
                }
                
                # Add fallback stats
                fallback = self._fallback._compute_stats(self._fallback.records)
                stats["fallback_records"] = fallback["total"]
                stats["memory_index"] = False
                
                return stats
            except Exception as e:
                logger.error(f"ES stats error: {e}")
        
        # Fallback
        return self._fallback.get_stats()
    
    # ─── Management ────────────────────────────────────────
    
    def delete_all(self) -> int:
        """Delete all documents from the ES index."""
        if self.available:
            try:
                resp = self._es.delete_by_query(
                    index=self._index_name,
                    body={"query": {"match_all": {}}},
                    refresh=True,
                )
                es_deleted = resp.get("deleted", 0)
                mem_deleted = self._fallback.delete_all()
                return es_deleted + mem_deleted
            except Exception as e:
                logger.error(f"ES delete error: {e}")
        return self._fallback.delete_all()
    
    def get_total_count(self) -> int:
        """Get total document count."""
        if self.available:
            try:
                resp = self._es.count(index=self._index_name)
                return resp.get("count", 0) + len(self._fallback.records)
            except:
                pass
        return len(self._fallback.records)
    
    def get_keywords(self) -> list:
        """Get list of distinct keywords in the index."""
        if self.available:
            try:
                body = {
                    "query": {"match_all": {}},
                    "size": 0,
                    "aggs": {
                        "keywords": {
                            "terms": {"field": "keyword", "size": 100}
                        }
                    }
                }
                resp = self._es.search(index=self._index_name, body=body)
                buckets = resp.get("aggregations", {}).get("keywords", {}).get("buckets", [])
                return [b["key"] for b in buckets]
            except:
                pass
        # Fallback: extract from memory
        keywords = set()
        for r in self._fallback.records:
            kw = r.get("keyword")
            if kw:
                keywords.add(kw)
        return list(keywords)


# ─── Singleton for global use ────────────────────────────────

_index_instance = None

def get_index() -> ElasticsearchIndex:
    """Get or create the global index singleton."""
    global _index_instance
    if _index_instance is None:
        _index_instance = ElasticsearchIndex()
    return _index_instance


# ─── CLI Test ────────────────────────────────────────────────

if __name__ == "__main__":
    idx = get_index()
    print(f"📊 ElasticsearchIndex available: {idx.available}")
    print(f"📦 Total records: {idx.get_total_count()}")
    print(f"🔑 Keywords: {idx.get_keywords()}")
    
    # Index a test record
    test_rec = {
        "id": "test_001",
        "keyword": "comcast",
        "email": "user@comcast.net",
        "domain": "comcast.net",
        "record_type": "email:pass",
        "severity": "high",
        "source_type": "test",
        "content_preview": "user@comcast.net:password123***",
        "discovered_at": datetime.now().isoformat(),
        "discovered_date": datetime.now().strftime("%Y-%m-%d"),
    }
    idx.index_record(test_rec)
    print(f"✅ Test record indexed")
    
    # Search
    results = idx.search(query_text="comcast")
    print(f"🔍 Search 'comcast': {results['total']} results in {results['took_ms']}ms")
    if results.get("stats"):
        print(f"📊 Stats: {json.dumps(results['stats'], indent=2)}")
    
    idx.delete_all()
    print(f"🗑️  Deleted all records")
