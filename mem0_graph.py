import os
os.chdir("H:/your path")
import re
import json
import time
import random
import requests
import uuid, datetime
from pathlib import Path
from neo4j import GraphDatabase
from mem0.client.main import APIError
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from dotenv import load_dotenv
from mem0 import Memory
from mem0 import MemoryClient
import json_file
load_dotenv()
os.environ["OPENAI_API_KEY"] = "sk-proj-"
os.environ["MRM0_API_KEY"] = "m0-"
# Update custom instructions
custom_instructions = """
Generate personal memories that follow these guidelines:

1. Each memory should be self-contained with complete context, including:
   - The person's name, do not use "user" while creating memories
   - Personal details (career aspirations, hobbies, life circumstances)
   - Emotional states and reactions
   - Ongoing journeys or future plans
   - Specific dates when events occurred

2. Include meaningful personal narratives focusing on:
   - Identity and self-acceptance journeys
   - Family planning and parenting
   - Creative outlets and hobbies
   - Mental health and self-care activities
   - Career aspirations and education goals
   - Important life events and milestones

3. Make each memory rich with specific details rather than general statements
   - Include timeframes (exact dates when possible)
   - Name specific activities (e.g., "charity race for mental health" rather than just "exercise")
   - Include emotional context and personal growth elements

4. Format each memory as a paragraph with a clear narrative structure that captures the person's experience, challenges, and aspirations
"""
BASE = Path(__file__).resolve().parent
VEC_DIR = BASE / "qdrant_data"
print(VEC_DIR)
config = {
    "llm": {
        "provider": "openai",
        "config": {
            "model": "gpt-4o-mini",
            "temperature": 0.2,
            "max_tokens": 2048,
        },
    },
    "vector_store": {
        "provider": "qdrant",
        "config": {
            "path": str(Path(r"H:/your qdrant path").resolve()),
            "collection_name": "mem0_vectors", # 所有进程共用
            "on_disk": True
        },
    },
    "graph_store": {
        "provider": "neo4j",
        "config": {
            "url": "bolt://localhost:7687",
            "username": "neo4j",
            "password": "nahida_happy_birthday"
        },
        "llm" : {
        "provider": "openai",
        "config": {
            "model": "gpt-4o-mini",
            "temperature": 0.0,
            "max_tokens": 2048}
            }
        }
}

class MemoryADD:
    def __init__(self, data_path=None, batch_size=2, is_graph=False):
        print(os.getenv("MEM0_API_KEY"))
        print(os.getenv("MEM0_ORGANIZATION_ID"))
        print(os.getenv("MEM0_PROJECT_ID"))
        self.mem0_client = MemoryClient(
            api_key=os.getenv("MEM0_API_KEY"),
            org_id=os.getenv("MEM0_ORGANIZATION_ID"),
            project_id=os.getenv("MEM0_PROJECT_ID"),
        )
        self.mem0_client.update_project(custom_instructions=custom_instructions)
        self.batch_size = batch_size
        self.data_path = data_path
        self.data = None
        self.is_graph = is_graph
        if data_path:
            self.load_data()

    def load_data(self):
        with open(self.data_path, "r") as f:
            self.data = json.load(f)
        return self.data

    def add_memory(self, user_id, message, metadata, retries=3):
        for attempt in range(retries):
            try:
                _ = self.mem0_client.add(
                    message, user_id=user_id, version="v2", metadata=metadata, enable_graph=self.is_graph
                )
                return
            except Exception as e:
                if attempt < retries - 1:
                    time.sleep(1)  # Wait before retrying
                    continue
                else:
                    raise e

    def add_memory_task(self, speaker, data):
        user_messga,assistant_message="",""
        for i in data:
            if i["author"]=="User":
                user_messga=i["content"]
            else:
                assistant_message=i["content"]
        messages = [
            {"role": "user", "content": user_messga},
            {"role": "assistant", "content": assistant_message},
        ]
        print("user:",messages[0]["content"][:10],"---","assistant:",messages[1]["content"][:20])
        now = datetime.now()
        iso_time = now.strftime("%Y-%m-%dT%H:%M:%S")
        try:
            self.add_memory(speaker, messages, metadata={"timestamp": iso_time})
            return True
        except Exception as e:
            print(f"插入出错: {e}")
            time.sleep(100)
            return False

    def add_memories_for_speaker_multithread(self, json_file, speaker="alian", max_workers=8):
        start_idx = 0
        all_data = [json_file[i:i + 2] for i in range(start_idx, len(json_file), 2) if i + 1 < len(json_file)]

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            time.sleep(random.uniform(1, 3))
            futures = [executor.submit(self.add_memory_task, speaker, data) for data in all_data]
            # 可选：显示进度
            for i, future in enumerate(as_completed(futures)):
                if future.result():
                    print(f"[{i + 1}/{len(futures)}] 插入成功")
                else:
                    print(f"[{i + 1}/{len(futures)}] 插入失败")

    async def delete_message(self):
        page = 6
        all_memories = []
        while True:
            try:
                batch = self.mem0_client.get_all(
                    version="v2",
                    user_id="alian",
                    page=page,
                    page_size=1000
                )
                if not batch:  # 拉完了
                    break
                for i in batch["results"]:
                    print(f"page:{page} 时间: {i.get('created_at', '')}\n内容: {i.get('memory', '')}\n是否删除？请按y/n")
                    choice = input().strip().lower()
                    if choice == "y":
                        memory_id = i["id"]
                        self.mem0_client.delete(memory_id)
                        print(f"{memory_id} 已删除")
                    else:
                        print("已保留\n")
                # all_memories.extend(batch["results"])
                page += 1
            except APIError as e:
                if "Invalid page" in str(e):
                    print("所有数据拉取完毕")
                    break
                else:
                    raise

class GraphMemory:
    _mem_singleton = None
    _neo_driver = None
    @staticmethod
    def mem():
        if GraphMemory._mem_singleton is None:
            GraphMemory._mem_singleton = Memory.from_config(config)
        return GraphMemory._mem_singleton

    @staticmethod
    def neo():
        if GraphMemory._neo_driver is None:
            gs = config["graph_store"]["config"]
            GraphMemory._neo_driver = GraphDatabase.driver(
                gs["url"], auth=(gs["username"], gs["password"])
            )
        return GraphMemory._neo_driver
    def __init__(self):
        self.nahida_memory = GraphMemory.mem()
        self.nahida_memory.should_write = lambda *_: True
        self.driver_neo4j = GraphMemory.neo()
        # import pdb; pdb.set_trace()
        print("vector_store.path",self.nahida_memory.vector_store)
        print("vector_store.collection_name",self.nahida_memory.vector_store.collection_name)

    def test_graph(self):
        results = self.nahida_memory.get_all(user_id="nahida_happy_birthday")
        for item in results["results"]:
            print("记忆节点：", item)
        for rel in results["relations"]:
            print("关系：", rel)
    def add_turn(self, session_id, turn_idx, role, text, user_id="nahida_happy_birthday"):
        def is_uuid(val):
            return bool(re.match(r'^[0-9a-fA-F\-]{36}$', str(val)))

        def _create_utterance(tx, mid, sid, turn, role, ts):
            """会存在一条text 生成多条mem0id的关键词，所以需要让所有mem0id 都绑定在这条sesstionid上"""
            tx.run(
                """
                MERGE (u:Utterance {mem0_id:$mid})
                SET u.session_id=$sid,
                u.turn=$turn,
                u.role=$role,
                u.content=$content,
                u.created_at=$ts
                """,
                mid=mid, sid=sid, turn=turn, role=role, content=text, ts=ts
            )
        try:
            res = self.nahida_memory.add(text, user_id=user_id)
        except Exception as e:
            print(f"[ERROR] add失败，text={text}... 错误信息: {e}")
            return None
        res_message= " ".join(data["id"]+" "+data["event"]+"\t" for data in res['results'])
        print(f"session_id:{session_id} ResInformation:{res_message}")
        mem0_id = None
        if isinstance(res, dict):
            if res.get("results"):
                for node in res["results"]:
                    mem0_id = node.get("id")
                    # 校验 UUID，插入 Neo4j
                    if is_uuid(mem0_id):
                        with self.driver_neo4j.session() as s:
                            s.execute_write(_create_utterance,
                                            mem0_id, session_id, turn_idx, role,
                                            datetime.utcnow().isoformat())
        return mem0_id

    def link_turns(self,session_id: str):
        """在同一 session 内按照 turn 建 :NEXT 边"""
        cypher = """
        MATCH (a:Utterance {session_id:$sid})
        WITH a ORDER BY a.turn ASC
        WITH collect(a) AS allUtter
        UNWIND range(0,size(allUtter)-2) AS idx
        WITH allUtter[idx]  AS u1, allUtter[idx+1] AS u2
        MERGE (u1)-[:NEXT]->(u2)
        """
        with self.driver_neo4j.session() as s:
            s.run(cypher, sid=session_id)

    def add_graph_memory(self, user_id, memory_message):
        sid = str(uuid.uuid4())  # 每轮会话一个 session_id
        user_messga, assistant_message = "", ""
        for i in memory_message:
            if i["author"] == "User":
                user_messga = i["content"]
            else:
                assistant_message = i["content"]
        if user_messga and assistant_message:
            self.add_turn(sid, 1, "user", user_messga, user_id)
            self.add_turn(sid, 2, "assistant", assistant_message, user_id)
            self.link_turns(sid)
            print(f"sid:{sid},user:{user_messga[-20:]},assistant:{assistant_message[:20]}")

    def add_memories_for_speaker_multithread(self, json_file, speaker="nahida_happy_birthday", max_workers=8):
        def worker(chunk):
            try:
                self.add_graph_memory(chunk, speaker)
                return True
            except Exception as e:
                print("❌", e)
                return False

        def pairwise_memories(contents):
            idx = 0
            while idx < len(contents) - 1:
                first = contents[idx]
                second = contents[idx + 1]
                if first["author"] == "User" and second["author"] == "ChatGPT":
                    yield [first, second]
                    idx += 2
                else:
                    idx += 1
        all_data = list(pairwise_memories(json_file.contents))[5:10]
        for data in all_data:
           print(f"user:", data[0]["author"], "message:", data[0]["content"][-20:],
                  "---", "assistant:", data[1]["author"], "message:", data[1]["content"][:20])

        with ThreadPoolExecutor(max_workers=max_workers) as exe:
            for i, ok in enumerate(exe.map(worker, all_data), start=1):
                print(f"[{i}/{len(all_data)}] {'✓' if ok else '✗'}")

    def search_graph_memory(self,user_id,prompt):
        results=self.nahida_memory.search(prompt,user_id=user_id)
        for item in results["results"]:
            print("记忆节点：", item)
        for rel in results["relations"]:
            print("关系：", rel)

    def search_and_stringify(self,user_id:str,prompt: str, top_k=3):
        def _stringify_dialogues(mem_nodes, top_k):
            """按 session-id 聚合去重；返回多段完整对话"""
            dialogs, seen_sid = [], set()
            with self.driver_neo4j.session() as s:
                for mn in mem_nodes:
                    mem0_id = mn["id"]
                    # 找到 mem0_id → session_id
                    sid = s.run("MATCH (u:Utterance {mem0_id:$mid}) RETURN u.session_id AS sid",mid=mem0_id).single()
                    if not sid or sid["sid"] in seen_sid:
                        continue
                    else: sid=sid["sid"]
                    seen_sid.add(sid)

                    # 再把同一 session 的所有轮次拼回来
                    q = """
                    MATCH (u:Utterance {session_id:$sid})
                    RETURN u.role AS role, u.turn AS turn, u.content AS content
                    ORDER BY u.turn
                    """
                    turns = [r.data() for r in s.run(q, sid=sid)]

                    unique_contents = set() #存在多条mem0id（信息条）对应同一个sessionid，所以需要按照role，rurn，content去重
                    unique_turns = []
                    for t in turns:
                        content_key = (t["role"], t["turn"], t["content"])
                        if content_key not in unique_contents:
                            unique_contents.add(content_key)
                            unique_turns.append(t)
                    dialogs.append("\n".join(f"[{t['role']}]：{t['content']}".replace("\n", "\t") for t in unique_turns))
                    if len(dialogs) >= top_k:
                        break
            return "\n---\n".join(dialogs)

        res = self.nahida_memory.search(prompt, user_id=user_id,limit=top_k)
        for item in res["results"]:
            print("记忆节点：", item)
        for rel in res["relations"]:
            print("关系：", rel)
        mem_nodes = res.get("results", [])
        mem_nodes=[data for data in mem_nodes if data["score"]>0.35]
        memory_infomation =""

        if mem_nodes:
            memory_infomation += ("\n【overview】:\n" + " | ".join(f"{r['memory']}" for r in mem_nodes))
            memory_infomation += "\n【hitstory message】:\n" + _stringify_dialogues(mem_nodes, top_k)
        rels = res.get("relations", [])
        if rels:
            memory_infomation += ("\n【relationship】:\n" + " | ".join(f"{r['source']} {r['relationship']} {r['destination']}" for r in rels))
        return memory_infomation if memory_infomation else "（未检索到可读记忆）"

    def delete_all(self):
        with self.driver_neo4j.session() as s:
            s.run("MATCH (n) DETACH DELETE n;")
        offset = None
        while True:
            points, next_page = self.nahida_memory.vector_store.client.scroll(collection_name="mem0_vectors", offset=offset)
            if not points:
                break
            batch = [p.id for p in points]
            self.nahida_memory.vector_store.client.delete(collection_name="mem0_vectors", points_selector=batch)
            offset = next_page
            if not offset:
                break

def add_memories_for_speaker_multithread(json_file, speaker="nahida_happy_birthday", max_workers=8):
    def pairwise_memories(contents):
        idx = 0
        while idx < len(contents) - 1:
            first = contents[idx]
            second = contents[idx + 1]
            if first["author"] == "User" and second["author"] == "ChatGPT":
                yield [first, second]
                idx += 2
            else:
                idx += 1
    def add_memory(data):
        url = "http://127.0.0.1:5001/add_memory"
        data = {
            "user": speaker,
            "memory_messages": data
        }
        resp = requests.post(url, json=data)
        print(resp.json())
        if not resp.json()["success"]:
            time.sleep(100)
        return resp.json()
    # all_data = list(pairwise_memories(json_file.contents))[1250:1300] # [1000:1100]
    all_data = list(pairwise_memories(json_file.new_contents3))
    for data in all_data:
       print(f"user:", data[0]["author"], "message:", data[0]["content"][-20:],
              "---", "assistant:", data[1]["author"], "message:", data[1]["content"][:20])
    with ThreadPoolExecutor(max_workers=max_workers) as exe:
        for i, ok in enumerate(exe.map(add_memory, all_data), start=1):
            ok=ok["success"]
            print(f"[{i}/{len(all_data)}] {'✓' if ok else '✗'}")

speaker="nahida_happy_birthday"
def add_memory(data):
    url = "http://127.0.0.1:5001/add_memory"
    data = {
        "user": speaker,
        "memory_messages": data
    }
    resp = requests.post(url, json=data)
    print(resp.json())
    if not resp.json()["success"]:
        time.sleep(100)
    return resp.json()
def search_post_memory(speaker, query,top_k):
    url = "http://127.0.0.1:5001/search_memory"
    data = {
        "user": speaker,
        "query": query,
        "top_k":top_k
    }
    resp = requests.post(url, json=data)
    print(resp.json())

# add_memory([{"author":"User","content":"[2025-07-02 00:32:04] 我正在测试最小化的永久记忆程序，尝试调通"},
#             {"author":"ChatGPT","content":"好的，祝你顺利调通"}])
print(search_post_memory(speaker,"记忆",3))
{'result':
     '\n【overview】:\n喜欢记录美好回忆 | 喜欢记录地图记忆 | 珍藏心愿与回忆\n'
     '【hitstory message】:\n[user]：2025-10-12 19:08:14(用户：我自己)\t1\n[assistant]：2\n[user]：(用户：我自己)\t1\n[assistant]：2\n'
     '【relationship】:\n阳光 渗进 记忆 | 故事权 重塑 记忆 | 旅行者 珍藏 记忆 | 心情 与 记忆 | 小果树 产生 回忆果', 'success': True}