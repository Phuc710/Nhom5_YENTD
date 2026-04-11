package com.example.cameraai.data

import android.util.Log
import com.example.cameraai.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * SePay API client — chạy server-side check CK qua Bearer token
 * Doc: https://my.sepay.vn/userapi
 *
 * QUAN TRỌNG: SEPAY_TOKEN không được để trong app release.
 * Production nên gọi qua backend của mình hoặc Supabase Edge Function.
 * File này chỉ dành cho demo/dev.
 */
object SePayClient {

    private val http = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .build()

    private const val BASE_URL = "https://my.sepay.vn/userapi"

    /**
     * Kiểm tra xem giao dịch với payment_code đã xuất hiện trên SePay chưa.
     * Match theo: amount + content chứa payment_code
     *
     * @return true nếu tìm thấy giao dịch khớp
     */
    suspend fun checkPayment(
        paymentCode: String,
        amount: Int,
    ): SePayResult = withContext(Dispatchers.IO) {
        try {
            val token = BuildConfig.SEPAY_TOKEN
            if (token == "your_sepay_access_token_here") {
                Log.w("SePay", "SEPAY_TOKEN chưa được cấu hình!")
                return@withContext SePayResult.NotFound
            }

            // Query danh sách giao dịch gần nhất
            val req = Request.Builder()
                .url("$BASE_URL/transactions/list?limit=20")
                .header("Authorization", "Bearer $token")
                .header("Content-Type", "application/json")
                .get()
                .build()

            val resp = http.newCall(req).execute()
            if (!resp.isSuccessful) {
                Log.w("SePay", "SePay HTTP ${resp.code}")
                return@withContext SePayResult.Error("HTTP ${resp.code}")
            }

            val body   = resp.body?.string() ?: return@withContext SePayResult.NotFound
            val json   = JSONObject(body)
            val txList = json.optJSONArray("transactions") ?: return@withContext SePayResult.NotFound

            for (i in 0 until txList.length()) {
                val tx = txList.getJSONObject(i)
                val content   = tx.optString("content", "")
                val amountIn  = tx.optInt("amount_in", 0)
                val txId      = tx.optString("id", "")
                val reference = tx.optString("reference_number", "")

                // Match: số tiền đúng + nội dung chứa payment_code
                if (amountIn >= amount && content.contains(paymentCode, ignoreCase = true)) {
                    Log.i("SePay", "✓ Payment match: $txId | $content | $amountIn")
                    return@withContext SePayResult.Paid(
                        transactionId = txId,
                        referenceCode = reference,
                        content = content,
                        amountIn = amountIn,
                    )
                }
            }

            Log.d("SePay", "No match for paymentCode=$paymentCode amount=$amount")
            SePayResult.NotFound

        } catch (e: Exception) {
            Log.e("SePay", "checkPayment error: ${e.message}")
            SePayResult.Error(e.message ?: "Unknown error")
        }
    }
}

sealed class SePayResult {
    object NotFound : SePayResult()
    data class Paid(
        val transactionId: String,
        val referenceCode: String,
        val content:       String,
        val amountIn:      Int,
    ) : SePayResult()
    data class Error(val message: String) : SePayResult()
}
