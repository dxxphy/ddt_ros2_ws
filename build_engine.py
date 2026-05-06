import tensorrt as trt
import sys
import os

ONNX_FILE_PATH = 'model_6000.onnx'
# 直接存为 C++ 代码里写死的名字，省得去改源码
ENGINE_FILE_PATH = 'model_gn.engine' 

def build_engine():
    logger = trt.Logger(trt.Logger.WARNING)
    builder = trt.Builder(logger)
    
    # 允许显式批处理 (Explicit Batch)
    network = builder.create_network(1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH))
    parser = trt.OnnxParser(network, logger)

    print(f"正在加载 ONNX 模型: {ONNX_FILE_PATH}")
    if not os.path.exists(ONNX_FILE_PATH):
        print(f"错误: 找不到文件 {ONNX_FILE_PATH}")
        sys.exit(1)

    with open(ONNX_FILE_PATH, 'rb') as model:
        if not parser.parse(model.read()):
            print('错误: 解析 ONNX 文件失败.')
            for error in range(parser.num_errors):
                print(parser.get_error(error))
            sys.exit(1)

    print("解析成功！开始使用 TensorRT 编译 Engine (这可能需要几分钟，请耐心等待)...")
    config = builder.create_builder_config()
    
    # 编译引擎
    serialized_engine = builder.build_serialized_network(network, config)

    if serialized_engine is None:
        print("错误: Engine 编译失败.")
        sys.exit(1)

    with open(ENGINE_FILE_PATH, 'wb') as f:
        f.write(serialized_engine)

    print(f"🎉 成功！Engine 已保存到: {ENGINE_FILE_PATH}")

if __name__ == '__main__':
    build_engine()
