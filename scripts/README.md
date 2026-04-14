A tool for generating Python code from .proto files.

To use:
1. Copy or create your `.proto` files in the `proto` folder at the root of this workspace.
   - Use `proto/api/onyx.proto` for the main API definitions.
   - Use `proto/common/common.proto` for shared definitions.
   - Place required Google dependencies (like `annotations.proto` or `http.proto`) inside `proto/google/api/`.
2. Run the script:
   - On Windows: `.\scripts\codegen.ps1`
   - On Linux/macOS: `./scripts/codegen.sh`

Dependencies:
`pip install grpcio-tools mypy-protobuf`
