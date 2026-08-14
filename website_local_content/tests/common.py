# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import io


def make_test_image():
    """A real (PIL-generated) JPEG, as image.mixin rejects fake payloads."""
    from PIL import Image

    image = Image.new("RGB", (64, 48), (10, 120, 160))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return base64.b64encode(buffer.getvalue())


def create_taxonomy(env, suffix="X"):
    """A content type with one category and one subcategory."""
    content_type = env["website.local.content.type"].create(
        {
            "name": f"Test Type {suffix}",
            "code": f"test_type_{suffix.lower()}",
            "url_slug": f"test-type-{suffix.lower()}",
            "use_photo_year": True,
        }
    )
    category = env["website.local.content.category"].create(
        {"name": f"Test Category {suffix}", "type_id": content_type.id}
    )
    subcategory = env["website.local.content.subcategory"].create(
        {"name": f"Test Subcategory {suffix}", "category_id": category.id}
    )
    return content_type, category, subcategory
