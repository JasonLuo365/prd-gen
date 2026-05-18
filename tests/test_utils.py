from prd_flow.utils import generate_doc_id


def test_generate_doc_id():
    assert generate_doc_id("my project") == "MY-PROJECT-v1.0"
    assert generate_doc_id("ecommerce_platform") == "ECOMMERCE-PLATFORM-v1.0"
