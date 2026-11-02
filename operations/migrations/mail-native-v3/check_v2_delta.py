"""Reject any production delta beyond the closed DDL comparison change."""
import ast
from pathlib import Path

base=Path(__file__).resolve().parent
before=ast.parse((base.parent/'mail-native/adopt.py').read_text())
after=ast.parse((base/'adopt.py').read_text())
after.body=[node for node in after.body if not (
    isinstance(node,ast.FunctionDef) and node.name in ('ddl_tokens','schema_objects') or
    isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id=='DDL_TOKEN')]


class RestoreComparison(ast.NodeTransformer):
    def visit_Name(self,node):
        if node.id=='schema_objects':node.id='objects'
        return node


after=RestoreComparison().visit(after)
assert ast.dump(before)==ast.dump(after),'Unexpected production change outside DDL token comparison'
print('ONLY_DDL_TOKEN_COMPARISON_CHANGED')
