package ai.ishara.demo.recognition.pipeline

import ai.ishara.demo.recognition.landmarks.KaggleLayout
import ai.ishara.demo.recognition.landmarks.LogitsModel
import org.tensorflow.lite.DataType
import org.tensorflow.lite.Interpreter
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * [LogitsModel] backed by LiteRT, running the ASL Signs 1st-place `asl-signs.tflite` on the CPU
 * (XNNPACK, 2 threads), as SignPipelineLiteRT does on iOS. The input's time dimension is
 * dynamic, so the input tensor is resized whenever the clip length changes. Not thread-safe:
 * build and use it on the recognition worker.
 */
class LiteRTLogitsModel(model: ByteBuffer) : LogitsModel, AutoCloseable {
    private val interpreter = Interpreter(model, Interpreter.Options().setNumThreads(THREADS).setUseXNNPACK(true))
    private var allocatedFrames: Int? = null

    /** The number of classes the model scores (250). */
    val classCount: Int

    init {
        try {
            classCount = checkSignature()
        } catch (error: Exception) {
            interpreter.close()
            throw error
        }
    }

    override fun logits(landmarks: FloatArray, frameCount: Int): FloatArray {
        checkInput(landmarks, frameCount)
        if (allocatedFrames != frameCount) {
            allocatedFrames = null
            interpreter.resizeInput(0, intArrayOf(frameCount, KaggleLayout.POINTS, KaggleLayout.COORDINATES))
            interpreter.allocateTensors()
            allocatedFrames = frameCount
        }
        val input = ByteBuffer.allocateDirect(landmarks.size * Float.SIZE_BYTES).order(ByteOrder.nativeOrder())
        input.asFloatBuffer().put(landmarks)
        val output = ByteBuffer.allocateDirect(classCount * Float.SIZE_BYTES).order(ByteOrder.nativeOrder())
        interpreter.run(input, output)
        output.rewind()
        val logits = FloatArray(classCount).also { output.asFloatBuffer().get(it) }
        if (!logits.all { it.isFinite() }) throw LiteRTModelException("non-finite output")
        return logits
    }

    override fun close() = interpreter.close()

    /** One float32 input `[frames, 543, 3]`, one float32 output; returns the class count. */
    private fun checkSignature(): Int {
        if (interpreter.inputTensorCount != 1 || interpreter.outputTensorCount != 1) {
            throw LiteRTModelException("expected one input and one output")
        }
        val input = interpreter.getInputTensor(0)
        val output = interpreter.getOutputTensor(0)
        if (input.dataType() != DataType.FLOAT32 || output.dataType() != DataType.FLOAT32) {
            throw LiteRTModelException("expected float32 tensors")
        }
        val dims = input.shapeSignature()
        if (dims.size != 3 || dims[1] != KaggleLayout.POINTS || dims[2] != KaggleLayout.COORDINATES) {
            throw LiteRTModelException("input ${dims.contentToString()}, expected [frames, 543, 3]")
        }
        val classes = output.numElements()
        if (classes < 2) throw LiteRTModelException("output has $classes values")
        return classes
    }

    class LiteRTModelException(message: String) : IllegalStateException(message)

    companion object {
        const val MODEL_ASSET = "asl-signs.tflite"
        const val THREADS = 2

        /** The values must be exactly [frameCount] Kaggle frames. */
        fun checkInput(landmarks: FloatArray, frameCount: Int) {
            require(frameCount > 0 && landmarks.size == frameCount * KaggleLayout.VALUES_PER_FRAME) {
                "expected $frameCount Kaggle frames, got ${landmarks.size} values"
            }
        }
    }
}
