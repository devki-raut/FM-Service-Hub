import base64
from pathlib import Path
from urllib.parse import quote

import fitz

from app.models import ImageReference, Source


VISUAL_TERMS = {
    "architecture",
    "diagram",
    "figure",
    "image",
    "internal",
    "layout",
    "photo",
    "picture",
    "show",
    "visual",
}

VISUAL_ASSET_DIR = Path("generated") / "visuals"
VISUAL_ASSET_URL_PREFIX = "/assets/visuals"


def images_for_question(question: str, sources: list[Source], limit: int = 1) -> list[ImageReference]:
    if not _asks_for_visual(question):
        return []

    images = []
    seen = set()
    for source in sources:
        if not source.page or not source.document_name.lower().endswith(".pdf"):
            continue
        key = (source.document_name, source.page)
        if key in seen:
            continue
        seen.add(key)

        path = _resolve_source_pdf(source.document_name)
        if not path:
            continue
        image_path = _render_pdf_page(path, source.page)
        if not image_path:
            continue
        images.append(
            ImageReference(
                document_name=source.document_name,
                page=source.page,
                url=f"{VISUAL_ASSET_URL_PREFIX}/{quote(image_path.name)}",
                data_url=_image_data_url(image_path),
                caption=f"{source.document_name}, page {source.page}",
            )
        )
        if len(images) >= limit:
            break
    return images


def _asks_for_visual(question: str) -> bool:
    lowered = question.casefold()
    return any(term in lowered for term in VISUAL_TERMS)


def _resolve_source_pdf(document_name: str) -> Path | None:
    candidates = [Path(document_name), Path("FM SERVICE HUB") / document_name, Path.cwd() / document_name]
    for candidate in candidates:
        if candidate.exists() and candidate.suffix.casefold() == ".pdf":
            return candidate
    for candidate in Path.cwd().rglob(document_name):
        if candidate.is_file() and candidate.suffix.casefold() == ".pdf":
            return candidate
    return None


def _render_pdf_page(path: Path, page: int) -> Path | None:
    if page < 1:
        return None
    VISUAL_ASSET_DIR.mkdir(parents=True, exist_ok=True)
    output = VISUAL_ASSET_DIR / f"{path.stem}-page-{page}.png"
    if output.exists():
        return output

    with fitz.open(path) as doc:
        if page > doc.page_count:
            return None
        pixmap = doc[page - 1].get_pixmap(matrix=fitz.Matrix(1.75, 1.75), alpha=False)
        pixmap.save(output)
    return output

def _image_data_url(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"