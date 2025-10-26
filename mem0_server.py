from flask import Flask, request, jsonify
import mem0_graph
graph_memory=mem0_graph.GraphMemory()
app = Flask(__name__)
@app.route('/add_memory', methods=['POST'])
def api_add_memory():
    try:
        data = request.get_json(force=True)
        user = data.get('user', 'alian')
        memory_messages = data['memory_messages']
        # **直接调用同步写，别用Thread！**
        res=graph_memory.add_graph_memory(user,memory_messages)
        return jsonify({"success": True, "result": res}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/search_memory', methods=['POST'])
def api_search_memory():
    try:
        data = request.get_json(force=True)
        user = data.get('user', 'alian')
        memory_messages = data['query']
        top_k=data['top_k']
        # **直接调用同步写，别用Thread！**
        res=graph_memory.search_and_stringify(user,memory_messages,top_k)
        return jsonify({"success": True, "result": res}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    if input("本作品服务于ml妲厨，沾屎妲厨不配。请输入Y/N？").strip().lower()=="Y":
        app.run(host='0.0.0.0', port=5001)