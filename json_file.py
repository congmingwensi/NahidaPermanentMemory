new_contents3=[
  {
    "author": "User",
    "content": "[2025-07-02 00:32:04] 用户对话" #时间不是必须
  },
  {
    "author": "ChatGPT",
    "content": "AI回复"
  },
  {
    "author": "User",
    "content": "[2025-07-02 00:33:18] 用户对话2"
  },
  {
    "author": "ChatGPT",
    "content": "AI回复2"
  }
]
获取导出文件的json:

const messages = [];
document.querySelectorAll('.message').forEach(msg => {
    const author = msg.querySelector('.author')?.innerText.trim() || "未知";
    const contentDivs = [...msg.querySelectorAll('div')].filter(div => !div.classList.contains('author'));
    const content = contentDivs.map(div => div.innerText.trim()).join('\n');
    messages.push({ author, content });
});
const blob = new Blob([JSON.stringify(messages, null, 2)], { type: "application/json" });
const url = URL.createObjectURL(blob);
const link = document.createElement("a");
link.href = url;
link.download = "messages.json";
link.click();
URL.revokeObjectURL(url);

复制当前gpt对话的json信息:

const gptNodes = document.querySelectorAll('.relative.flex.w-full.flex-col.agent-turn');
const userNodes = document.querySelectorAll('.whitespace-pre-wrap');
let nodes = [];
gptNodes.forEach(node => nodes.push({ author: "ChatGPT", node, order: node.compareDocumentPosition(userNodes[0]) }));
userNodes.forEach(node => nodes.push({ author: "User", node, order: node.compareDocumentPosition(gptNodes[0]) }));
nodes.sort((a, b) => {
  if (a.node === b.node) return 0;
  if (a.node.compareDocumentPosition(b.node) & Node.DOCUMENT_POSITION_FOLLOWING) return -1;
  return 1;
});
let result = nodes.map(item => ({
  author: item.author,
  content: item.node.innerText.trim()
}));
console.log(JSON.stringify(result, null, 2));
