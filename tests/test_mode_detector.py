from prd_flow.mode_detector import Mode, detect_mode


def test_explicit_root_declaration():
    """User explicitly states this is a project beginning."""
    result = detect_mode(
        user_input="这是一个新项目，我要做一个电商平台",
        parent_prd=None,
        parent_architecture=None,
        target_module=None,
    )
    assert result == Mode.ROOT


def test_derive_with_all_inputs():
    """All derive inputs provided."""
    result = detect_mode(
        user_input="生成支付模块的PRD",
        parent_prd="parent_prd.md",
        parent_architecture="arch.md",
        target_module="payment_gateway",
    )
    assert result == Mode.DERIVE


def test_derive_with_architecture_package():
    """Architecture package can replace legacy parent_architecture."""
    result = detect_mode(
        user_input="鐢熸垚鏀粯妯″潡鐨凱RD",
        parent_prd="parent_prd.md",
        parent_architecture=None,
        architecture_package="architecture",
        target_module="payment_gateway",
    )
    assert result == Mode.DERIVE


def test_missing_target_defaults_to_root():
    """Missing target_module falls back to root."""
    result = detect_mode(
        user_input="生成PRD",
        parent_prd="parent.md",
        parent_architecture="arch.md",
        target_module=None,
    )
    assert result == Mode.ROOT
