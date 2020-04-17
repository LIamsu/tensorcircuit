from functools import partial
from typing import Tuple, List

import numpy as np
import tensornetwork as tn
import graphviz

from . import gates
from .cons import npdtype, backend


class Circuit:
    def __init__(self, nqubits: int) -> None:
        _prefix = "qb-"
        if nqubits < 2:
            raise ValueError(
                f"Number of qubits must be greater than 2 but is {nqubits}."
            )

        # Get nodes on the interior
        nodes = [
            tn.Node(
                np.array([[[1.0]], [[0,]]], dtype=npdtype), name=_prefix + str(x + 1),
            )
            for x in range(nqubits - 2)
        ]

        # Get nodes on the end
        nodes.insert(
            0, tn.Node(np.array([[1.0], [0,]], dtype=npdtype), name=_prefix + str(0),),
        )
        nodes.append(
            tn.Node(
                np.array([[1.0], [0,]], dtype=npdtype), name=_prefix + str(nqubits - 1),
            )
        )

        # Connect edges between middle nodes
        for i in range(1, nqubits - 2):
            tn.connect(nodes[i].get_edge(2), nodes[i + 1].get_edge(1))

        # Connect end nodes to the adjacent middle nodes
        if nqubits < 3:
            tn.connect(nodes[0].get_edge(1), nodes[1].get_edge(1))
        else:
            tn.connect(
                nodes[0].get_edge(1), nodes[1].get_edge(1)
            )  # something wrong here?
            tn.connect(nodes[-1].get_edge(1), nodes[-2].get_edge(2))

        self._nqubits = nqubits
        self._nodes = nodes
        self._front = [n.get_edge(0) for n in nodes]
        self._start = nodes
        self._meta_appy()

    def _meta_appy(self) -> None:
        sgates = ["i", "x", "y", "z", "h"] + ["cnot", "cz", "swap"] + ["toffoli"]
        for g in sgates:
            setattr(self, g, partial(self.apply_general_gate, getattr(gates, g)()))
            setattr(
                self, g.upper(), partial(self.apply_general_gate, getattr(gates, g)())
            )

    def apply_single_gate(self, gate: tn.Node, index: int) -> None:
        gate.get_edge(0) ^ self._front[index]
        self._front[index] = gate.get_edge(1)
        self._nodes.append(gate)

    def apply_double_gate(self, gate: tn.Node, index1: int, index2: int) -> None:
        assert index1 != index2
        gate.get_edge(0) ^ self._front[index1]
        gate.get_edge(1) ^ self._front[index2]
        self._front[index1] = gate.get_edge(2)
        self._front[index2] = gate.get_edge(3)
        self._nodes.append(gate)

    def apply_general_gate(self, gate: tn.Node, *index: int) -> None:
        assert len(index) == len(set(index))
        noe = len(index)
        for i, ind in enumerate(index):
            gate.get_edge(i) ^ self._front[ind]
            self._front[ind] = gate.get_edge(i + noe)
        self._nodes.append(gate)

    def _copy(self) -> Tuple[List[tn.Node], List[tn.Edge]]:
        ndict, edict = tn.copy(self._nodes)
        newnodes = []
        for n in self._nodes:
            newnodes.append(ndict[n])
        newfront = []
        for e in self._front:
            newfront.append(edict[e])
        return newnodes, newfront

    def wavefunction(self) -> tn.Node.tensor:
        nodes, d_edges = self._copy()
        t = tn.contractors.greedy(nodes, output_edge_order=d_edges)
        return backend.reshape(t.tensor, shape=[1, -1])

    def amplitude(self, l: str) -> tn.Node.tensor:
        assert len(l) == self._nqubits
        no, d_edges = self._copy()
        ms = []
        for i, s in enumerate(l):
            if s == "1":
                ms.append(
                    tn.Node(np.array([0, 1], dtype=npdtype), name=str(i) + "-measure")
                )
            elif s == "0":
                ms.append(
                    tn.Node(np.array([1, 0], dtype=npdtype), name=str(i) + "-measure")
                )
        for i, n in enumerate(l):
            d_edges[i] ^ ms[i].get_edge(0)

        no.extend(ms)
        return tn.contractors.greedy(no).tensor

    def to_graphviz(
        self,
        graph: graphviz.Graph = None,
        include_all_names: bool = False,
        engine: str = "neato",
    ) -> graphviz.Graph:
        nodes = self._nodes
        if graph is None:
            # pylint: disable=no-member
            graph = graphviz.Graph("G", engine=engine)
        for node in nodes:
            if not node.name.startswith("__") or include_all_names:
                label = node.name
            else:
                label = ""
            graph.node(str(id(node)), label=label)
        seen_edges = set()
        for node in nodes:
            for i, edge in enumerate(node.edges):
                if edge in seen_edges:
                    continue
                seen_edges.add(edge)
                if not edge.name.startswith("__") or include_all_names:
                    edge_label = edge.name + ": " + str(edge.dimension)
                else:
                    edge_label = ""
                if edge.is_dangling():
                    # We need to create an invisible node for the dangling edge
                    # to connect to.
                    graph.node(
                        "{}_{}".format(str(id(node)), i),
                        label="",
                        _attributes={"style": "invis"},
                    )
                    graph.edge(
                        "{}_{}".format(str(id(node)), i),
                        str(id(node)),
                        label=edge_label,
                    )
                else:
                    graph.edge(
                        str(id(edge.node1)), str(id(edge.node2)), label=edge_label,
                    )
        return graph
