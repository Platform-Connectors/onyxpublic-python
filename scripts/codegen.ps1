# Get correct paths
$repoRoot = (Get-Item -Path "$PSScriptRoot/..").FullName
$protoDir = "$repoRoot/proto"
$srcDir = "$repoRoot/src/onyxpublic"

Write-Host "Generating Python protobuf definitions....." -ForegroundColor Cyan

# Use --python_out, --grpc_python_out, etc. to actually generate files
# We output to 'src' so the internal directory structure matches the package: 'api/onyx.proto' -> 'src/api/onyx_pb2.py'
# NOTE: To get 'src/onyxpublic/api/onyx_pb2.py', we set out to 'src/onyxpublic'
python -m grpc_tools.protoc `
    --proto_path="$protoDir" `
    --proto_path="$protoDir/google/api" `
    --python_out="$srcDir" `
    --grpc_python_out="$srcDir" `
    --mypy_out="$srcDir" `
    --mypy_grpc_out="$srcDir" `
    "$protoDir/api/onyx.proto" `
    "$protoDir/common/common.proto"

Write-Host "Fixing imports to use package imports..." -ForegroundColor Green

# Fix imports in onyx_pb2.py to use relative/absolute imports that work with the package structure
# Typically: 'from common import common_pb2' -> 'from onyxpublic.common import common_pb2'
Get-ChildItem -Path "$srcDir/api" -Filter "onyx_pb2*.py" | ForEach-Object {
    $content = Get-Content -Path $_.FullName -Raw
    $newContent = $content -replace "from common import common_pb2", "from onyxpublic.common import common_pb2"
    Set-Content -Path $_.FullName -Value $newContent
    Write-Host "  Fixed $($_.Name)"
}

Write-Host "Generation complete." -ForegroundColor Green
