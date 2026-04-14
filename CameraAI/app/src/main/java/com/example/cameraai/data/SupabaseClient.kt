package com.example.cameraai.data

import android.util.Log
import io.github.jan.supabase.createSupabaseClient
import io.github.jan.supabase.postgrest.Postgrest
import io.github.jan.supabase.postgrest.query.Order
import io.github.jan.supabase.storage.Storage
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import com.example.cameraai.BuildConfig
import com.example.cameraai.data.model.Violation
import com.example.cameraai.data.model.ViolationPayment

/** Singleton Supabase client — query trực tiếp, không qua backend */
object SupabaseClient {

    val client by lazy {
        createSupabaseClient(
            supabaseUrl  = BuildConfig.SUPABASE_URL,
            supabaseKey  = BuildConfig.SUPABASE_ANON
        ) {
            install(Postgrest)
            install(Storage)
        }
    }

    // ── Tra cứu biển số — check xem có vi phạm không ─────────────
    suspend fun checkPlateExists(normalizedPlate: String): Boolean =
        withContext(Dispatchers.IO) {
            try {
                val res = client.postgrest["view_violations_full"]
                    .select {
                        filter { eq("license_plate_normalized", normalizedPlate) }
                        limit(1)
                    }
                res.decodeList<Map<String, Any?>>().isNotEmpty()
            } catch (e: Exception) {
                Log.e("Supabase", "checkPlateExists: ${e.message}", e)
                false
            }
        }

    // ── Load toàn bộ vi phạm theo biển số ────────────────────────
    suspend fun getViolationsByPlate(
        normalizedPlate: String,
        fromDate: String? = null,
        toDate:   String? = null,
        limit:    Int     = 100,
        offset:   Int     = 0,
    ): List<Violation> = withContext(Dispatchers.IO) {
        try {
            val res = client.postgrest["view_violations_full"]
                .select {
                    filter {
                        eq("license_plate_normalized", normalizedPlate)
                        if (fromDate != null) gte("timestamp", fromDate)
                        if (toDate   != null) lte("timestamp", toDate)
                    }
                    order("timestamp", Order.DESCENDING)
                    range(offset.toLong(), (offset + limit - 1).toLong())
                }
            res.decodeList<Violation>()
        } catch (e: Exception) {
            Log.e("Supabase", "getViolationsByPlate: ${e.message}", e)
            emptyList()
        }
    }

    // ── Chi tiết 1 vi phạm ────────────────────────────────────────
    suspend fun getViolationDetail(id: Int): Violation? =
        withContext(Dispatchers.IO) {
            try {
                client.postgrest["view_violations_full"]
                    .select { filter { eq("id", id) } }
                    .decodeSingle<Violation>()
            } catch (e: Exception) {
                Log.e("Supabase", "getViolationDetail($id): ${e.message}", e)
                null
            }
        }

    // ── Lấy payment mới nhất cho violation ───────────────────────
    suspend fun getPayment(violationId: Int): ViolationPayment? =
        withContext(Dispatchers.IO) {
            try {
                val res = client.postgrest["violation_payments"]
                    .select {
                        filter { eq("violation_id", violationId) }
                        order("created_at", Order.DESCENDING)
                        limit(1)
                    }
                res.decodeList<ViolationPayment>().firstOrNull()
            } catch (e: Exception) {
                Log.e("Supabase", "getPayment($violationId): ${e.message}", e)
                null
            }
        }

    /**
     * Tạo payment record.
     * Anon key bị RLS block INSERT → trả null thay vì crash.
     * PaymentActivity sẽ dùng local-generated payment nếu null.
     */
    suspend fun createPayment(payment: ViolationPayment): ViolationPayment? =
        withContext(Dispatchers.IO) {
            try {
                client.postgrest["violation_payments"]
                    .insert(payment) { select() }
                    .decodeSingle<ViolationPayment>()
            } catch (e: Exception) {
                // RLS sẽ block anon insert — bình thường, trả null
                Log.w("Supabase", "createPayment skipped (likely RLS): ${e.message}")
                null
            }
        }

    // ── Lưu plate session (anon INSERT được phép theo RLS) ───────
    suspend fun saveSession(plate: String, normalizedPlate: String, deviceId: String) {
        withContext(Dispatchers.IO) {
            try {
                client.postgrest["plate_sessions"]
                    .upsert(
                        mapOf(
                            "license_plate"            to plate,
                            "license_plate_normalized" to normalizedPlate,
                            "device_id"                to deviceId
                        )
                    )
            } catch (e: Exception) {
                Log.w("Supabase", "saveSession: ${e.message}")
            }
        }
    }
}
