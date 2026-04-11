from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urldefrag, urljoin, urlparse, urlunparse

import aiohttp
import networkx as nx
from bs4 import BeautifulSoup

from graph_layout import compute_partitioned_layout
from quantum import build_webpage_feature_circuit, circuit_png_bytes, extract_features
from state import AppState


DEFAULT_HEADERS = {
    "User-Agent": "KLQuantumCrawler/1.0 (+https://localhost)",
    "Accept": "text/html,application/xhtml+xml",
}


@dataclass
class CrawlConfig:
    seed_url: str
    max_pages: int = 50
    max_depth: int = 2
    concurrency: int = 5
    request_timeout: int = 15
    same_domain_only: bool = True

    def as_dict(self) -> Dict[str, object]:
        return {
            "seed_url": self.seed_url,
            "max_pages": self.max_pages,
            "max_depth": self.max_depth,
            "concurrency": self.concurrency,
            "request_timeout": self.request_timeout,
            "same_domain_only": self.same_domain_only,
        }


class CrawlerController:
    def __init__(self, state: AppState):
        self.state = state
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._processed_count = 0

    def start(self, config: CrawlConfig) -> None:
        with self.state.lock:
            if self.state.running:
                raise RuntimeError("Crawler is already running.")
        self._stop_event = threading.Event()
        self.state.reset(config.as_dict())
        self._thread = threading.Thread(
            target=self._thread_main,
            args=(config,),
            daemon=True,
            name="kl-quantum-crawler",
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self.state.stop()

    def _thread_main(self, config: CrawlConfig) -> None:
        try:
            asyncio.run(self._crawl_async(config))
        except Exception as exc:
            self.state.publish({"type": "error", "message": f"Crawler crashed: {exc}"})
            self.state.finish("Crawler crashed")

    async def _crawl_async(self, config: CrawlConfig) -> None:
        normalized_seed = normalize_url(config.seed_url)
        seed_host = host_of(normalized_seed)
        queue: asyncio.Queue[Tuple[str, int, Optional[str]]] = asyncio.Queue()
        await queue.put((normalized_seed, 0, None))

        seen: Set[str] = {normalized_seed}
        processed_count_lock = asyncio.Lock()
        self._processed_count = 0

        with self.state.lock:
            self.state.queued_count = 1
            self.state.graph.add_node(
                normalized_seed,
                url=normalized_seed,
                domain=seed_host,
                status="queued",
                depth=0,
                title="",
                label=compact_label(normalized_seed),
                features={},
            )
        self._publish_snapshot("Seed queued")

        timeout = aiohttp.ClientTimeout(total=config.request_timeout)
        connector = aiohttp.TCPConnector(limit=max(2, config.concurrency * 2), ssl=False)

        async with aiohttp.ClientSession(timeout=timeout, headers=DEFAULT_HEADERS, connector=connector) as session:
            workers = [
                asyncio.create_task(
                    self._worker(
                        session=session,
                        queue=queue,
                        seen=seen,
                        seed_host=seed_host,
                        config=config,
                        processed_count_lock=processed_count_lock,
                    )
                )
                for _ in range(config.concurrency)
            ]

            try:
                await queue.join()
            finally:
                for _ in workers:
                    await queue.put(("__STOP__", 0, None))
                await asyncio.gather(*workers, return_exceptions=True)

        if self._stop_event.is_set():
            self.state.finish("Crawler stopped by user")
        else:
            self.state.finish("Crawler finished")
        self._publish_snapshot("Final snapshot")

    async def _worker(
        self,
        *,
        session: aiohttp.ClientSession,
        queue: asyncio.Queue[Tuple[str, int, Optional[str]]],
        seen: Set[str],
        seed_host: str,
        config: CrawlConfig,
        processed_count_lock: asyncio.Lock,
    ) -> None:
        while True:
            url, depth, parent = await queue.get()
            if url == "__STOP__":
                queue.task_done()
                return

            if self._stop_event.is_set() or not self.state.running:
                queue.task_done()
                continue

            async with processed_count_lock:
                current_count = self._processed_count
                if current_count >= config.max_pages:
                    queue.task_done()
                    continue
                self._processed_count = current_count + 1

            self._mark_node(url, status="fetching", depth=depth)
            self._publish_snapshot(f"Fetching {url}")

            try:
                page = await fetch_page(session, url)
                links = extract_links(page["html"], base_url=url)
                if config.same_domain_only:
                    links = [link for link in links if host_of(link) == seed_host]
                filtered_links = [link for link in links if is_probably_html(link)]

                internal_ratio = 0.0
                if filtered_links:
                    internal_ratio = sum(1 for link in filtered_links if host_of(link) == host_of(url)) / len(filtered_links)

                title = page["title"]
                text = page["text"]
                unique_word_ratio = 0.0
                if text["word_count"]:
                    unique_word_ratio = min(1.0, text["unique_word_count"] / max(1, text["word_count"]))

                page_info = {
                    "url": url,
                    "depth": depth,
                    "domain": host_of(url),
                    "status": "crawled",
                    "title": title,
                    "label": compact_label(url),
                    "link_count": len(filtered_links),
                    "internal_ratio": round(internal_ratio, 4),
                    "text_length": text["text_length"],
                    "word_count": text["word_count"],
                    "unique_word_ratio": round(unique_word_ratio, 4),
                    "title_length": len(title),
                    "content_type": page["content_type"],
                }
                values, named_features = extract_features(page_info)
                qc = build_webpage_feature_circuit(values, compact_label(url))
                png = circuit_png_bytes(qc)
                self.state.set_latest_circuit(
                    png,
                    {
                        "url": url,
                        "title": title,
                        "features": named_features,
                        "depth": depth,
                    },
                )

                self._mark_node(url, **page_info, features=named_features)
                with self.state.lock:
                    self.state.visited_count += 1

                if depth < config.max_depth:
                    newly_queued = 0
                    for link in filtered_links:
                        self._add_edge(url, link)
                        if link not in seen:
                            seen.add(link)
                            await queue.put((link, depth + 1, url))
                            newly_queued += 1
                            self._mark_node(
                                link,
                                domain=host_of(link),
                                status="queued",
                                depth=depth + 1,
                                title="",
                                label=compact_label(link),
                                features={},
                            )
                    with self.state.lock:
                        self.state.queued_count += newly_queued

                self._publish_snapshot(f"Crawled {url}")
            except Exception as exc:
                self._mark_node(url, status="error", error=str(exc), depth=depth)
                with self.state.lock:
                    self.state.error_count += 1
                self.state.publish({"type": "error", "message": f"{url}: {exc}"})
                self._publish_snapshot(f"Error on {url}")
            finally:
                queue.task_done()

    def _mark_node(self, node_id: str, **attrs: object) -> None:
        with self.state.lock:
            if not self.state.graph.has_node(node_id):
                self.state.graph.add_node(node_id)
            self.state.graph.nodes[node_id].update(attrs)
            self.state.graph.nodes[node_id].setdefault("url", node_id)
            self.state.graph.nodes[node_id].setdefault("label", compact_label(node_id))
            self.state.graph.nodes[node_id].setdefault("domain", host_of(node_id))

    def _add_edge(self, source: str, target: str) -> None:
        with self.state.lock:
            if self.state.graph.has_edge(source, target):
                self.state.graph[source][target]["weight"] = self.state.graph[source][target].get("weight", 1) + 1
            else:
                self.state.graph.add_edge(source, target, weight=1)

    def _publish_snapshot(self, message: str) -> None:
        payload = graph_payload(self.state.graph)
        self.state.publish(
            {
                "type": "snapshot",
                "message": message,
                "graph": payload,
                "meta": self.state.snapshot_meta(),
            }
        )


def graph_payload(graph: nx.DiGraph) -> Dict[str, List[Dict[str, object]]]:
    positions = compute_partitioned_layout(graph)
    nodes: List[Dict[str, object]] = []
    for node, data in graph.nodes(data=True):
        pos = positions.get(node, {"x": 0.0, "y": 0.0, "group": 0})
        nodes.append(
            {
                "id": node,
                "url": data.get("url", node),
                "label": data.get("label") or compact_label(node),
                "title": data.get("title", ""),
                "domain": data.get("domain", host_of(node)),
                "status": data.get("status", "unknown"),
                "depth": int(data.get("depth", 0)),
                "group": int(pos.get("group", 0)),
                "x": float(pos.get("x", 0.0)),
                "y": float(pos.get("y", 0.0)),
                "features": data.get("features", {}),
                "content_type": data.get("content_type", ""),
                "error": data.get("error", ""),
            }
        )
    edges = [{"source": u, "target": v, "weight": data.get("weight", 1)} for u, v, data in graph.edges(data=True)]
    return {"nodes": nodes, "edges": edges}


async def fetch_page(session: aiohttp.ClientSession, url: str) -> Dict[str, object]:
    async with session.get(url, allow_redirects=True) as response:
        content_type = response.headers.get("Content-Type", "")
        if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
            raise RuntimeError(f"Unsupported content type: {content_type or 'unknown'}")
        html = await response.text(errors="ignore")

    soup = BeautifulSoup(html, "html.parser")
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    text = soup.get_text(" ", strip=True)
    words = [token for token in text.split() if token]
    unique_words = set(word.lower() for word in words)
    return {
        "html": html,
        "title": title,
        "content_type": content_type,
        "text": {
            "text_length": len(text),
            "word_count": len(words),
            "unique_word_count": len(unique_words),
        },
    }


def extract_links(html: str, *, base_url: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    links: List[str] = []
    seen: Set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = (anchor.get("href") or "").strip()
        if not href:
            continue
        abs_url = normalize_url(urljoin(base_url, href))
        if not abs_url or abs_url in seen:
            continue
        seen.add(abs_url)
        links.append(abs_url)
    return links


def normalize_url(url: str) -> str:
    if not url:
        return ""
    url, _fragment = urldefrag(url.strip())
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return ""
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    cleaned = parsed._replace(netloc=netloc, path=path)
    return urlunparse(cleaned)


def is_probably_html(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower()
    blocked_suffixes = (
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".svg",
        ".webp",
        ".pdf",
        ".zip",
        ".rar",
        ".7z",
        ".mp3",
        ".mp4",
        ".mov",
        ".avi",
        ".css",
        ".js",
        ".xml",
        ".json",
        ".csv",
    )
    return not path.endswith(blocked_suffixes)


def host_of(url: str) -> str:
    return urlparse(url).netloc.lower()


def compact_label(url: str, max_len: int = 34) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    leaf = path.split("/")[-1] if path else ""
    label = host if not leaf else f"{host}/{leaf}"
    if len(label) <= max_len:
        return label
    return label[: max_len - 1] + "…"
