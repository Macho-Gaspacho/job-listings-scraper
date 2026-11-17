"""Ready search links. No network."""

from source_map import Recommendation
from link_outs import write_links


def test_welcome_to_the_jungle_link_encodes_role_and_place(tmp_path):
    recommendation = Recommendation(
        sources=(),
        link_outs=("welcome_to_the_jungle",),
        explanation=(),
    )
    path = tmp_path / "links.md"
    count = write_links(path, recommendation, ["data analyst"], ["Amsterdam, Netherlands"])
    text = path.read_text(encoding="utf-8")
    assert count == 1
    assert "Welcome to the Jungle" in text
    assert "data+analyst" in text
    assert "Amsterdam%2C+Netherlands" in text
    assert text.endswith("These sites do not allow automatic reading, so open them yourself.\n")
