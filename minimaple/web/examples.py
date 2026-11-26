"""Voorbeelden voor de voorbeeldenlijst in de UI."""
EXAMPLES = [
    {"title": "Afgeleide en integraal", "code": "f := x -> x^2*sin(x):\ndiff(f(x), x);\nint(f(x), x);\nint(f(x), x = 0..Pi);"},
    {"title": "Limiet en reeks", "code": "limit(sin(x)/x, x = 0);\nseries(exp(x), x = 0, 6);\nsum(1/k^2, k = 1..infinity);"},
    {"title": "Vergelijkingen", "code": "solve(x^2 - 3*x + 2 = 0, x);\nsolve({x + y = 3, x - y = 1}, {x, y});"},
    {"title": "Differentiaalvergelijking", "code": "dsolve(diff(y(x), x, x) + y(x) = 0, y(x));\ndsolve({diff(y(x), x) = y(x), y(0) = 2}, y(x));"},
    {"title": "Matrices", "code": "with(LinearAlgebra):\nA := Matrix([[2, 1], [1, 2]]);\nDeterminant(A);\nEigenvalues(A);\nA^(-1);"},
    {"title": "Plot 2D", "code": "plot(sin(x)/x, x = -10..10, color = red, title = \"sinc\");"},
    {"title": "Plot 3D", "code": "plot3d(sin(x)*cos(y), x = -Pi..Pi, y = -Pi..Pi);"},
    {"title": "Vectorcalculus", "code": "with(VectorCalculus):\nSetCoordinates('cartesian'[x, y, z]):\nF := VectorField(<x*y, y*z, z*x>):\nDivergence(F);\nCurl(F);"},
    {"title": "Laplace-transformatie", "code": "with(inttrans):\nlaplace(exp(-2*t)*sin(3*t), t, s);\ninvlaplace(1/(s^2 + 1), s, t);"},
    {"title": "Numeriek", "code": "evalf(Pi, 30);\nevalf(Int(exp(-x^2), x = 0..1));"},
]
