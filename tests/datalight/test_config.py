from datalight.config import DatalightConfig


def test_load_minimal_yaml_config_and_render_topic_prompts(tmp_path):
    cfg_path = tmp_path / "datalight.yaml"
    cfg_path.write_text(
        """
mineru:
  executable: /opt/mineru/bin/mineru

output:
  root: .tmp/datalight_outputs

qa:
  topic: OpenClaw 的架构和部署

prompts:
  singlehop_system: |
    只围绕以下 Topic 生成 QA：
    {topic}
  evaluator_system: |
    只评估以下 Topic 相关 QA：
    {topic}
llm:
  provider: lmstudio
  base_url: http://127.0.0.1:1234/v1
  model: gemma-4-31b-it
  timeout_sec: 180
  temperature: 0.1
""",
        encoding="utf-8",
    )

    cfg = DatalightConfig.from_file(cfg_path)

    assert cfg.mineru.executable == "/opt/mineru/bin/mineru"
    assert str(cfg.output.root) == ".tmp/datalight_outputs"
    assert cfg.qa.topic == "OpenClaw 的架构和部署"
    assert cfg.llm.provider == "lmstudio"
    assert cfg.llm.base_url == "http://127.0.0.1:1234/v1"
    assert cfg.llm.model == "gemma-4-31b-it"
    assert cfg.llm.timeout_sec == 180
    assert cfg.llm.temperature == 0.1
    assert "OpenClaw 的架构和部署" in cfg.prompt_config().render("singlehop", "")
    assert "OpenClaw 的架构和部署" in cfg.prompt_config().render("evaluator", "")


def test_empty_config_keeps_all_fields_optional(tmp_path):
    cfg_path = tmp_path / "empty.yaml"
    cfg_path.write_text("", encoding="utf-8")

    cfg = DatalightConfig.from_file(cfg_path)

    assert cfg.mineru.executable is None
    assert cfg.output.root is None
    assert cfg.llm.provider is None
    assert cfg.llm.base_url is None
    assert cfg.llm.model is None
    assert cfg.llm.timeout_sec is None
    assert cfg.llm.temperature is None
    assert cfg.qa.topic == ""
    assert cfg.prompt_config().render("singlehop", "default system") == "default system"
