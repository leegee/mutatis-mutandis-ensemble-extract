from mutatis_mutandis.lib.corpus_storage import local_dir, publish, fetch
(local_dir("source_tokens") / "smoke.txt").write_text("hello")
publish("source_tokens", "*.txt")
print(fetch("source_tokens", "*.txt"))
