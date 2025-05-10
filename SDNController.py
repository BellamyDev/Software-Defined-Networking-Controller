

import sys, shlex, hashlib, networkx as nx
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
#watermark = hashlib.sha256(("---" + "NeoDDaBRgX5a9").encode()).hexdigest()
#print(watermark)
#17d51df74873029615cfa0e9e981e1de7faf25382505c42f59b697dc77734a1f


G          = nx.Graph()            # topology
flow_tbl   = {}                    # switch -> list[(match, next_hop)]
link_load  = {}                    # edgge (u,v) -> packet count
VIPS       = {"A", "B"}            # priority endpoints
CRITICAL   = set()                 # flows requiring backup

# ---- HELPERS -------------------------------------------------------------
def k_paths(src, dst, k=2):
    try:
        return list(nx.shortest_simple_paths(G, src, dst, weight="cost"))[:k]
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return []

def add_rule(path, match):
    for u, v in zip(path, path[1:]):
        flow_tbl.setdefault(u, []).append((match, v))

def program_flow(src, dst):
    paths = k_paths(src, dst, k=1)    # just get the best path first
    if not paths:
        print(f"No path {src}->{dst}")
        return

    match = {"src": src, "dst": dst,
             "prio": (src in VIPS or dst in VIPS)}

    primary = paths[0]
    add_rule(primary, match)

    #  If critical, make a backup
    if (src, dst) in CRITICAL:
        #make a copy
        H = G.copy()
        # remove every edge in the primary from H
        for u, v in zip(primary, primary[1:]):
            if H.has_edge(u, v):
                H.remove_edge(u, v)

        # find the shortest path in H 
        try:
            backup = nx.shortest_path(H, src, dst, weight="cost")
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            backup = None

        if backup:
            add_rule(backup, {**match, "backup": True})
        else:
            print(f"No disjoint backup for {src}->{dst}")

def recompute():
    flow_tbl.clear()
    for key in set(link_load.keys()) | CRITICAL:
        if isinstance(key, tuple) and len(key) == 2 and key not in link_load:
            # skip edge‐counters
            continue
        src, dst = key
        program_flow(src, dst)

# ---- DRAW GRAPH --------------------------
def draw():
    fig = plt.gcf()

    plt.clf()
    fig.canvas.manager.set_window_title("17d51df74873029615cfa0e9e981e1de7faf25382505c42f59b697dc77734a1f")
    pos = nx.spring_layout(G)
    # base graph
    nx.draw_networkx_nodes(G, pos, node_size=400, node_color="lightblue")
    nx.draw_networkx_labels(G, pos)
    nx.draw_networkx_edges(G, pos, edge_color="lightgray", width=2)

    # legend
    handles = [
        Line2D([0], [0], color="blue", lw=4, label="primary"),
        Line2D([0], [0], color="red",  lw=3, linestyle="--", label="backup")
    ]

    # overlay per‐flow paths
    for (src, dst), pkts in link_load.items():
        if not isinstance(src, str) or not isinstance(dst, str):
            continue  # skip edge counters
        paths = k_paths(src, dst, k=2)
        if not paths:
            continue
        # primary path
        prim_edges = list(zip(paths[0], paths[0][1:]))
        nx.draw_networkx_edges(G, pos, edgelist=prim_edges,
                               edge_color="blue", width=4)
        # backup patj
        if (src, dst) in CRITICAL and len(paths) > 1:
            back_edges = list(zip(paths[1], paths[1][1:]))
            nx.draw_networkx_edges(G, pos, edgelist=back_edges,
                                   edge_color="red", style="dashed", width=3)

    # per‐link labels from link_load
    edge_labels = {}
    for u, v in G.edges():
        e = tuple(sorted((u, v)))
        edge_labels[(u, v)] = str(link_load.get(e, 0))
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_color="black")

    plt.legend(handles=handles, loc="upper left", fontsize="small")
    plt.axis("off")
    plt.pause(0.1)

# ---- CLI COMMANDS --------------------------------------------------------
def do_add_node(args):
    if len(args) != 1:
        print("Usage: add-node <name>"); return
    G.add_node(args[0])

def do_add_link(args):
    if len(args) < 2:
        print("Usage: add-link <n1> <n2> [cost]"); return
    cost = int(args[2]) if len(args) > 2 else 1
    G.add_edge(args[0], args[1], cost=cost)

def do_fail_link(args):
    if len(args) != 2:
        print("Usage: fail-link <n1> <n2>"); return
    try:
        G.remove_edge(args[0], args[1])
        recompute()
    except KeyError:
        print("Edge not found")

def do_send(args):
    if len(args) < 2:
        print("Usage: send <src> <dst> [pkts] [critical]"); return
    src, dst = args[0], args[1]
    pkts     = int(args[2]) if len(args) > 2 and args[2].isdigit() else 100
    crit     = (len(args) > 3 and args[3] == "critical")

    # record the flow itself
    link_load[(src, dst)] = link_load.get((src, dst), 0) + pkts
    if crit:
        CRITICAL.add((src, dst))

    # program per‐switch rules
    program_flow(src, dst)

    # show total load on the links
    primary = k_paths(src, dst, k=1)
    if primary:
        for u, v in zip(primary[0], primary[0][1:]):
            e = tuple(sorted((u, v)))
            link_load[e] = link_load.get(e, 0) + pkts

def do_show(args):
    # End‑to‑end paths
    print("Flows provisioned:")
    for (src, dst), pkts in link_load.items():
        if not isinstance(src, str): continue
        paths = k_paths(src, dst, k=2)
        if not paths:
            print(f"  {src}→{dst}: (no path)")
            continue
        print(f"  {src}→{dst}: primary = {'→'.join(paths[0])}")
        if (src, dst) in CRITICAL and len(paths) > 1:
            print(f"             backup  = {'→'.join(paths[1])}")

    # per‐switch table
    print("\nPer-switch flow tables:")
    for sw, rules in flow_tbl.items():
        print(f" {sw}:")
        for match, nh in rules:
            attrs = ",".join(f"{k}={v}" for k,v in match.items())
            print(f"    match[{attrs}] → {nh}")

    # show the graph
    draw()

def do_help(_):
    print("""Commands:
  add-node <N>
  add-link <A> <B> [cost]
  fail-link <A> <B>
  send <S> <D> [pkts] [critical]
  show
  help
  exit / quit""")

cmds = {
    "add-node":  do_add_node,
    "add-link":  do_add_link,
    "fail-link": do_fail_link,
    "send":      do_send,
    "show":      do_show,
    "help":      do_help
}

# ---- INTERACTIVE LkOOP ----------------------------------------------------
def repl():
    print("SDN CLI (type 'help' to list commands)")
    while True:
        try:
            line = input("controller> ").strip()
        except (KeyboardInterrupt, EOFError):
            print(); break
        if not line:
            continue
        if line in ("exit", "quit"):
            break
        parts = shlex.split(line)
        cmd, args = parts[0], parts[1:]
        fn = cmds.get(cmd)
        if fn:
            fn(args)
        else:
            print(f"Unknown command: {cmd}")

if __name__ == "__main__":
    repl()

