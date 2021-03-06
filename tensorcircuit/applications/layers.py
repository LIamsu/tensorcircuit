"""
module for functions adding layers of circuits
"""

import sys
import itertools
import numpy as np
import cirq
import networkx as nx
from typing import Sequence, Union, Callable, Any, Optional, Tuple, List

from ..circuit import Circuit
from ..gates import num_to_tensor

thismodule = sys.modules[__name__]

Tensor = Any  # tf.Tensor
Graph = Any  # nx.Graph
Symbol = Any  # sympy.Symbol


def generate_double_gate(gates: str) -> None:
    d1, d2 = gates[0], gates[1]

    def f(
        circuit: Circuit, qubit1: int, qubit2: int, symbol: Union[Tensor, float]
    ) -> Circuit:
        if d1 == "x":
            circuit.H(qubit1)  # type: ignore
        elif d1 == "y":
            circuit.rx(qubit1, theta=num_to_tensor(-np.pi / 2))  # type: ignore
        if d2 == "x":
            circuit.H(qubit2)  # type: ignore
        elif d2 == "y":
            circuit.rx(qubit2, theta=num_to_tensor(-np.pi / 2))  # type: ignore
        circuit.CNOT(qubit1, qubit2)  # type: ignore
        circuit.rz(qubit2, theta=symbol)  # type: ignore
        circuit.CNOT(qubit1, qubit2)  # type: ignore
        if d1 == "x":
            circuit.H(qubit1)  # type: ignore
        elif d1 == "y":
            circuit.rx(qubit1, theta=num_to_tensor(np.pi / 2))  # type: ignore
        if d2 == "x":
            circuit.H(qubit2)  # type: ignore
        elif d2 == "y":
            circuit.rx(qubit2, theta=num_to_tensor(np.pi / 2))  # type: ignore
        return circuit

    f.__doc__ = """%sgate""" % gates
    setattr(thismodule, gates + "gate", f)


def generate_gate_layer(gate: str) -> None:
    """
    $$e^{-i\theta \sigma}$$

    :param gate:
    :return:
    """

    def f(
        circuit: Circuit, symbol: Union[Tensor, float] = None, g: Graph = None
    ) -> Circuit:  # compatible with graph mode
        if gate.lower() in Circuit.sgates:
            for n in range(circuit._nqubits):
                getattr(circuit, gate)(n)
        else:
            for n in range(circuit._nqubits):
                getattr(circuit, gate)(n, theta=2 * symbol)
        return circuit

    f.__doc__ = """%slayer""" % gate
    f.__repr__ = """%slayer""" % gate  # type: ignore
    f.__trainable__ = False if gate in Circuit.sgates else True  # type: ignore
    setattr(thismodule, gate + "layer", f)


def generate_double_gate_layer(gates: str) -> None:
    def f(circuit: Circuit, symbol: Union[Tensor, float], g: Graph = None) -> Circuit:
        if g is None:
            g = nx.complete_graph(circuit._nqubits)
        for e in g.edges:
            qubit1, qubit2 = e
            getattr(thismodule, gates + "gate")(
                circuit, qubit1, qubit2, -symbol * g[e[0]][e[1]].get("weight", 1.0) * 2
            )  ## should be better as * 2 # e^{-i\theta H}, H=-ZZ
        return circuit

    f.__doc__ = """%slayer""" % gates
    f.__repr__ = """%slayer""" % gates  # type: ignore
    f.__trainable__ = True  # type: ignore
    setattr(thismodule, gates + "layer", f)


def generate_double_layer_block(gates: Tuple[str]) -> None:
    d1, d2 = gates[0], gates[1]  # type: ignore

    def f(circuit: Circuit, symbol: Tensor, g: Graph = None) -> Circuit:
        if g is None:
            g = nx.complete_graph(circuit._nqubits)
        getattr(thismodule, d1 + "layer")(circuit, symbol[0], g)
        getattr(thismodule, d2 + "layer")(circuit, symbol[1], g)
        return circuit

    f.__doc__ = """%s_%s_block""" % (d1, d2)
    f.__repr__ = """%s_%s_block""" % (d1, d2)  # type: ignore
    f.__trainable__ = False if (d1 in Circuit.sgates) and (d2 in Circuit.sgates) else True  # type: ignore
    setattr(thismodule, "%s_%s_block" % (d1, d2), f)


for gate in ["rx", "ry", "rz", "H", "I"]:
    generate_gate_layer(gate)

for gates in itertools.product(*[["x", "y", "z"] for _ in range(2)]):
    gates = gates[0] + gates[1]
    generate_double_gate(gates)  # type: ignore
    generate_double_gate_layer(gates)  # type: ignore

for gates in itertools.product(
    *[["rx", "ry", "rz", "xx", "yy", "zz"] for _ in range(2)]
):
    generate_double_layer_block(gates)  # type: ignore


## below is similar layer but in cirq API instead of tensrocircuit native API
## special notes to the API, the arguments order are different due to historical reason

basis_rotation = {
    "x": (cirq.H, cirq.H),
    "y": (cirq.rx(-np.pi / 2), cirq.rx(np.pi / 2)),
    "z": None,
}


def generate_qubits(g: Graph) -> List[Any]:
    return sorted([v for _, v in g.nodes.data("qubit")])


def generate_cirq_double_gate(gates: str) -> None:
    d1, d2 = gates[0], gates[1]
    r1, r2 = basis_rotation[d1], basis_rotation[d2]

    def f(
        circuit: cirq.Circuit,
        qubit1: cirq.GridQubit,
        qubit2: cirq.GridQubit,
        symbol: Symbol,
    ) -> cirq.Circuit:
        if r1 is not None:
            circuit.append(r1[0](qubit1))
        if r2 is not None:
            circuit.append(r2[0](qubit2))
        circuit.append(cirq.CNOT(qubit1, qubit2))
        circuit.append(cirq.rz(symbol)(qubit2))
        circuit.append(cirq.CNOT(qubit1, qubit2))
        if r1 is not None:
            circuit.append(r1[1](qubit1))
        if r2 is not None:
            circuit.append(r2[1](qubit2))
        return circuit

    f.__doc__ = """%sgate""" % gates
    setattr(thismodule, "cirq" + gates + "gate", f)


def cirqswapgate(
    circuit: cirq.Circuit,
    qubit1: cirq.GridQubit,
    qubit2: cirq.GridQubit,
    symbol: Symbol,
) -> cirq.Circuit:
    circuit.append(cirq.SwapPowGate(exponent=symbol)(qubit1, qubit2))
    return circuit


def cirqcnotgate(
    circuit: cirq.Circuit,
    qubit1: cirq.GridQubit,
    qubit2: cirq.GridQubit,
    symbol: Symbol,
) -> cirq.Circuit:
    circuit.append(cirq.CNOT(qubit1, qubit2))
    return circuit


def generate_cirq_gate_layer(gate: str) -> None:
    """
    $$e^{-i\theta \sigma}$$

    :param gate:
    :return:
    """

    def f(
        circuit: cirq.Circuit,
        g: Graph,
        symbol: Symbol,
        qubits: Optional[Sequence[Any]] = None,
    ) -> cirq.Circuit:
        if isinstance(symbol, list) or isinstance(symbol, tuple):
            symbol = symbol[0]
        if not qubits:
            qubits = generate_qubits(g)
        rotation = getattr(cirq, gate)
        if isinstance(rotation, cirq.Gate):
            circuit.append(rotation.on_each(qubits))
        else:  # function
            circuit.append(rotation(2.0 * symbol).on_each(qubits))
        return circuit

    f.__doc__ = """%slayer""" % gate
    f.__repr__ = """%slayer""" % gate  # type: ignore
    f.__trainable__ = False if isinstance(getattr(cirq, gate), cirq.Gate) else True  # type: ignore
    setattr(thismodule, "cirq" + gate + "layer", f)


def generate_cirq_any_gate_layer(gate: str) -> None:
    """
    $$e^{-i\theta \sigma}$$

    :param gate:
    :return:
    """

    def f(
        circuit: cirq.Circuit,
        g: Graph,
        symbol: Symbol,
        qubits: Optional[Sequence[Any]] = None,
    ) -> cirq.Circuit:
        if not qubits:
            qubits = generate_qubits(g)
        l = len(qubits)
        rotation = getattr(cirq, gate)
        for i, q in enumerate(qubits):
            circuit.append(rotation(2.0 * symbol[i])(q))
        return circuit

    f.__doc__ = """any%slayer""" % gate
    f.__repr__ = """any%slayer""" % gate  # type: ignore
    f.__trainable__ = True  # type: ignore
    setattr(thismodule, "cirqany" + gate + "layer", f)


def generate_cirq_double_gate_layer(gates: str) -> None:
    def f(
        circuit: cirq.Circuit,
        g: Graph,
        symbol: Symbol,
        qubits: Optional[Sequence[Any]] = None,
    ) -> cirq.Circuit:
        if isinstance(symbol, list) or isinstance(symbol, tuple):
            symbol = symbol[0]
        for e in g.edges:
            qubit1 = g.nodes[e[0]]["qubit"]
            qubit2 = g.nodes[e[1]]["qubit"]
            getattr(thismodule, "cirq" + gates + "gate")(
                circuit, qubit1, qubit2, -symbol * g[e[0]][e[1]]["weight"] * 2
            )  ## should be better as * 2 # e^{-i\theta H}, H=-ZZ
        return circuit

    f.__doc__ = """%slayer""" % gates
    f.__repr__ = """%slayer""" % gates  # type: ignore
    f.__trainable__ = True  # type: ignore
    setattr(thismodule, "cirq" + gates + "layer", f)


def generate_cirq_any_double_gate_layer(gates: str) -> None:
    """
    The following function generated layer should be used with special case,
    as its soundness depends on the nature of task or problem, it doesn't always make sense

    :param gates:
    :return:
    """

    def f(
        circuit: cirq.Circuit,
        g: Graph,
        symbol: Symbol,
        qubits: Optional[Sequence[Any]] = None,
    ) -> cirq.Circuit:
        for i, e in enumerate(g.edges):
            qubit1 = g.nodes[e[0]]["qubit"]
            qubit2 = g.nodes[e[1]]["qubit"]
            getattr(thismodule, "cirq" + gates + "gate")(
                circuit, qubit1, qubit2, -symbol[i] * g[e[0]][e[1]]["weight"] * 2
            )  ## should be better as * 2 # e^{-i\theta H}, H=-ZZ
        return circuit

    f.__doc__ = """%slayer""" % gates
    f.__repr__ = """%slayer""" % gates  # type: ignore
    f.__trainable__ = True  # type: ignore
    setattr(thismodule, "cirqany" + gates + "layer", f)


for gate in ["rx", "ry", "rz", "H"]:
    generate_cirq_gate_layer(gate)
    if gate != "H":
        generate_cirq_any_gate_layer(gate)

for gates in itertools.product(*[["x", "y", "z"] for _ in range(2)]):
    gates = gates[0] + gates[1]
    generate_cirq_double_gate(gates)  # type: ignore
    generate_cirq_double_gate_layer(gates)  # type: ignore
    generate_cirq_any_double_gate_layer(gates)  # type: ignore

generate_cirq_double_gate_layer("swap")
generate_cirq_any_double_gate_layer("swap")
generate_cirq_double_gate_layer("cnot")
