from app.logics.layout.validator import validate


def test_validate_accepts_card_with_allowed_content_and_table_sections():
    assert validate(
        "<card-title>Title</card-title>"
        "<card-body><p>Hello <strong>world</strong></p>"
        "<table><thead><tr><th>Heading</th></tr></thead>"
        "<tbody><tr><td>Value</td></tr></tbody></table>"
        "<p>Second paragraph</p></card-body>"
    )


def test_validate_requires_title_then_body_as_direct_children():
    assert not validate("<p>Generic fragment</p><p>Second root</p>")
    assert not validate(
        "<card-body><p>Text</p></card-body><card-title>Title</card-title>"
    )
    assert not validate(
        "<card-title>Title</card-title><card-body><p>Text</p></card-body>"
        "<p>Unexpected third element</p>"
    )


def test_validate_rejects_unknown_tags_and_attributes():
    assert not validate(
        "<card-title>Title</card-title>"
        "<card-body><script>alert('x')</script></card-body>"
    )
    assert not validate(
        "<card-title>Title</card-title>"
        '<card-body><p onclick="run()">Text</p></card-body>'
    )
    assert not validate(
        '<card-title class="title">Title</card-title><card-body><p>Text</p></card-body>'
    )
    assert not validate(
        '<card-title>Title</card-title><card-body class="body"><p>Text</p></card-body>'
    )


def test_validate_rejects_disallowed_nesting():
    assert not validate(
        "<card-title>Title</card-title>"
        "<card-body><p><span><div>Not allowed here</div></span></p></card-body>"
    )


def test_validate_rejects_content_in_document_head():
    assert not validate(
        "<head><title>Unexpected</title></head>"
        "<card-title>Title</card-title><card-body><p>Text</p></card-body>"
    )
