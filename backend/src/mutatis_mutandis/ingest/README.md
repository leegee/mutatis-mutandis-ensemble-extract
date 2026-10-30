```bash
$ python src/tier0/tier0_0_text2db.py --file enoch_charles_1917.xml --corpus misc
2026-10-28 08:48:08 [tier0] Process misc from G:\corpus\misc
2026-10-28 08:48:08 [tier0] Input directory: G:\corpus\misc
2026-10-28 08:48:08 [tier0] Found 1 XML files
2026-10-28 08:48:08 [tier0] Example: G:\corpus\misc\enoch_charles_1917.xml
2026-10-28 08:48:08 [tier0 worker 12496] received 1 misc files
2026-10-28 08:48:08 [tier0] enoch_charles_1917: year 1917 taken from publicationStmt(no usable imprint date)
2026-10-28 08:48:09 [tier0 worker 12496] finished: 1 docs processed

$ python src/passage_search_pipeline/ingest/passages_1_export_full.py --force-doc-id enoch_charles_1917
2026-10-28 08:48:27 Force mode: exporting ONLY doc_ids ['enoch_charles_1917'] (ignoring Lance, existing shards, and CORPUS_SQL); first new shard is 00000
2026-10-28 08:48:27 Wrote E:My Drive\passage-pipeline\source_tokens\tokens_00000.parquet (1 docs)
2026-10-28 08:48:27 Done: exported 1 documents

# Run on Colab `passages_2_0_colab_embed_passages.py` the continue here:

$ python src/passage_search_pipeline/ingest/passages_3_passages_parquet_to_lance.py
2026-10-28 08:51:20 [passages] input: E:\My Drive\passage-pipeline\passages
2026-10-28 08:51:20 [passages] Lance root: D:\src\mutatis-mutandis\out\indexes\lance_albinism
2026-10-28 08:51:20 [passages] found 1 shard(s)
2026-10-28 08:51:20 [passages] windowed text: False
2026-10-28 08:51:22 [passages] passages_00000.parquet: input passages=158, new vector rows=474
2026-10-28 08:51:22 [passages] indexing passage_l8__macberth__1900_1949: 781 rows, 27 partitions
2026-10-28 08:51:22 [passages] indexing passage_last__macberth__1900_1949: 781 rows, 27 partitions
2026-10-28 08:51:22 [passages] indexing passage_mean4__macberth__1900_1949: 781 rows, 27 partitions
2026-10-28 08:51:23 [passages] complete: passages read=158, new vector rows=474
2026-10-28 08:51:23 [passages] table passage_l8__macberth__1900_1949: 781 rows
2026-10-28 08:51:23 [passages] table passage_last__macberth__1900_1949: 781 rows
2026-10-28 08:51:23 [passages] table passage_mean4__macberth__1900_1949: 781 rows
```