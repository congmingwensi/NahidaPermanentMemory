"""User-scoped Neo4j reads and atomic memory writes."""
from uuid import uuid4

from neo4j import GraphDatabase

from .settings import MemorySettings


class Neo4jMemoryStore:
    def __init__(self, settings: MemorySettings):
        self.database = settings.neo4j_database
        self.driver = GraphDatabase.driver(settings.neo4j_uri,
                                          auth=(settings.neo4j_user, settings.neo4j_password),
                                          connection_timeout=10.0)

    def ensure_schema(self):
        statements = [
            "CREATE CONSTRAINT nahida_topic_id IF NOT EXISTS FOR (n:NahidaMemoryTopic) REQUIRE n.topic_id IS UNIQUE",
            "CREATE CONSTRAINT nahida_topic_name IF NOT EXISTS FOR (n:NahidaMemoryTopic) REQUIRE (n.user_id, n.name) IS UNIQUE",
            "CREATE CONSTRAINT nahida_entry_id IF NOT EXISTS FOR (n:NahidaMemoryEntry) REQUIRE n.entry_id IS UNIQUE",
            "CREATE CONSTRAINT nahida_message_id IF NOT EXISTS FOR (n:NahidaMemoryMessage) REQUIRE n.message_id IS UNIQUE",
        ]
        with self.driver.session(database=self.database) as session:
            for statement in statements:
                session.run(statement).consume()

    def list_topic_names(self, user_id: str) -> list[str]:
        """读取当前用户全部大字段名称，供 Agent 选择分类。"""
        with self.driver.session(database=self.database) as session:
            return session.execute_read(lambda tx: [row["name"] for row in tx.run(
                "MATCH (t:NahidaMemoryTopic {user_id:$user_id}) "
                "RETURN t.name AS name ORDER BY name", user_id=user_id,
            )])

    def list_topic_vectors(self, user_id: str) -> list[dict]:
        with self.driver.session(database=self.database) as session:
            return session.execute_read(lambda tx: tx.run(
                "MATCH (t:NahidaMemoryTopic {user_id:$user_id}) "
                "RETURN t.topic_id AS topic_id, t.name AS name, t.embedding AS embedding, "
                "t.embedding_model AS embedding_model", user_id=user_id
            ).data())

    def list_entry_vectors(self, user_id: str, topic_id: str) -> list[dict]:
        with self.driver.session(database=self.database) as session:
            return session.execute_read(lambda tx: tx.run(
                "MATCH (t:NahidaMemoryTopic {user_id:$user_id, topic_id:$topic_id})"
                "-[:HAS_ENTRY]->(e:NahidaMemoryEntry {user_id:$user_id}) "
                "RETURN e.entry_id AS entry_id, e.summary AS summary, e.memory_types AS memory_types, e.embedding AS embedding, "
                "e.embedding_model AS embedding_model", user_id=user_id, topic_id=topic_id
            ).data())

    def write_memory(self, record: dict, topic_vector: list[float], entry_vector: list[float],
                     model: str, topic_match: dict | None, entry_match: dict | None,
                     expected_old_summary: str | None = None) -> dict:
        topic_id = topic_match["topic_id"] if topic_match else str(uuid4())
        entry_id = entry_match["entry_id"] if entry_match else str(uuid4())
        name = topic_match["name"] if topic_match else record["topic"]
        message = record["message"]
        parameters = dict(user_id=record["user_id"], topic_id=topic_id, entry_id=entry_id,
                          name=name, topic_vector=topic_vector, entry_vector=entry_vector,
                          model=model, summary=record["summary"], memory_types=record["memory_types"],
                          now=record["updatetime"], message_id=message["message_id"],
                          content=message["content"], message_created_at=message["created_at"],
                          message_updatetime=message["updatetime"])
        query = """
        MERGE (t:NahidaMemoryTopic {user_id:$user_id, topic_id:$topic_id})
        ON CREATE SET t.name=$name, t.embedding=$topic_vector, t.embedding_model=$model,
                      t.created_at=$now, t.weight=0.0
        MERGE (e:NahidaMemoryEntry {user_id:$user_id, entry_id:$entry_id})
        ON CREATE SET e.created_at=$now, e.message_ids=[]
        SET e.summary=$summary, e.memory_types=$memory_types, e.embedding=$entry_vector,
            e.embedding_model=$model, e.updatetime=$now,
            e.message_ids=CASE WHEN $message_id IN coalesce(e.message_ids, [])
                              THEN e.message_ids ELSE coalesce(e.message_ids, []) + [$message_id] END
        MERGE (t)-[:HAS_ENTRY]->(e)
        MERGE (m:NahidaMemoryMessage {user_id:$user_id, message_id:$message_id})
        ON CREATE SET m.content=$content, m.created_at=$message_created_at, m.updatetime=$message_updatetime
        MERGE (e)-[:HAS_MESSAGE]->(m)
        SET t.updatetime=$now, t.weight=round((coalesce(t.weight,0.0)+0.1)*10.0)/10.0
        RETURN t.topic_id AS topic_id, t.name AS topic, t.weight AS weight,
               t.updatetime AS topic_updatetime, e.entry_id AS entry_id,
               e.created_at AS created_at, e.updatetime AS updatetime,
               e.summary AS summary, e.memory_types AS memory_types, e.message_ids AS message_ids
        """
        def write(tx):
            if expected_old_summary is not None:
                matches = tx.run(
                    "MATCH (t:NahidaMemoryTopic {user_id:$uid, topic_id:$tid})"
                    "-[:HAS_ENTRY]->(e:NahidaMemoryEntry {user_id:$uid, summary:$old}) "
                    "RETURN e.entry_id AS entry_id LIMIT 2",
                    uid=record["user_id"], tid=topic_id, old=expected_old_summary,
                ).data()
                if len(matches) != 1 or matches[0]["entry_id"] != entry_id:
                    return {"status": "conflict", "message": "目标概述已变化，请重新读取后定位"}
            return tx.run(query, **parameters).single(strict=True).data()

        with self.driver.session(database=self.database) as session:
            result = session.execute_write(write)
        if "status" in result:
            return result
        return {"status": "success", "tool": "memory_add",
                "topic_action": "matched" if topic_match else "created",
                "action": "overwritten" if entry_match else "created",
                "topic_similarity": topic_match.get("score") if topic_match else None,
                "entry_similarity": entry_match.get("score") if entry_match else None, **result}

    def find_update_target(self, user_id: str, topic: str, old_summary: str) -> dict:
        with self.driver.session(database=self.database) as session:
            rows = session.execute_read(lambda tx: tx.run(
                "MATCH (t:NahidaMemoryTopic {user_id:$uid, name:$name})"
                "-[:HAS_ENTRY]->(e:NahidaMemoryEntry {user_id:$uid, summary:$summary}) "
                "RETURN t{.topic_id,.name,.embedding,.embedding_model} AS topic, "
                "e{.entry_id} AS entry LIMIT 2", uid=user_id, name=topic, summary=old_summary,
            ).data())
        if not rows:
            return {"status": "not_found", "message": "当前用户下未找到对应大字段和旧概述"}
        if len(rows) > 1:
            return {"status": "ambiguous", "message": "旧概述命中多个小字段，请提供唯一目标"}
        return {"status": "success", **rows[0]}

    def increase_weight(self, user_id: str, topic: str, now: str) -> dict:
        with self.driver.session(database=self.database) as session:
            row = session.execute_write(lambda tx: tx.run(
                "MATCH (t:NahidaMemoryTopic {user_id:$uid, name:$name}) "
                "SET t.weight=round((coalesce(t.weight,0.0)+0.1)*10.0)/10.0, t.updatetime=$now "
                "RETURN t{.topic_id,.name,.weight,.created_at,.updatetime} AS topic",
                uid=user_id, name=topic, now=now,
            ).single())
        if row is None:
            return {"status": "not_found", "message": "当前用户下未找到对应大字段"}
        return {"status": "success", "topic": row["topic"]}

    @staticmethod
    def _read_entries(tx, user_id: str, topic_id: str, count: int | None = None,
                      cutoff: str | None = None) -> list[dict]:
        query = (
            "MATCH (t:NahidaMemoryTopic {user_id:$uid, topic_id:$tid})"
            "-[:HAS_ENTRY]->(e:NahidaMemoryEntry {user_id:$uid}) "
        )
        if cutoff is not None:
            query += "WHERE e.updatetime >= $cutoff "
        query += (
            "RETURN e{.entry_id,.summary,.memory_types,.created_at,.updatetime,.message_ids} AS entry "
            "ORDER BY e.updatetime DESC "
        )
        if count is not None:
            query += "LIMIT $count"
        return [row["entry"] for row in tx.run(query, uid=user_id, tid=topic_id, count=count, cutoff=cutoff)]

    @staticmethod
    def _validate_count(count: int):
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            raise ValueError("读取数量需要为正整数")

    def get_topic_entries(self, user_id: str, topic: str, count: int) -> dict | None:
        self._validate_count(count)

        def read(tx):
            row = tx.run(
                "MATCH (t:NahidaMemoryTopic {user_id:$uid, name:$name}) "
                "RETURN t{.topic_id,.name,.weight,.created_at,.updatetime} AS topic",
                uid=user_id, name=topic,
            ).single()
            if row is None:
                return None
            result = dict(row["topic"])
            result["entries"] = self._read_entries(tx, user_id, result["topic_id"], count=count)
            return result

        with self.driver.session(database=self.database) as session:
            return session.execute_read(read)

    def get_recent_topics(self, user_id: str, count: int, cutoff: str) -> list[dict]:
        self._validate_count(count)

        def read(tx):
            topics = [dict(row["topic"]) for row in tx.run(
                "MATCH (t:NahidaMemoryTopic {user_id:$uid}) "
                "RETURN t{.topic_id,.name,.weight,.created_at,.updatetime} AS topic "
                "ORDER BY t.updatetime DESC LIMIT $count", uid=user_id, count=count,
            )]
            for topic in topics:
                latest = self._read_entries(tx, user_id, topic["topic_id"], count=10)
                recent = self._read_entries(tx, user_id, topic["topic_id"], cutoff=cutoff)
                entries = {entry["entry_id"]: entry for entry in [*latest, *recent]}
                topic["entries"] = sorted(entries.values(), key=lambda entry: entry["updatetime"], reverse=True)
            return topics

        with self.driver.session(database=self.database) as session:
            return session.execute_read(read)

    def close(self):
        self.driver.close()
