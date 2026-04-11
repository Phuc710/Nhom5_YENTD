package com.example.cameraai.data.model

import android.os.Parcelable
import kotlinx.parcelize.Parcelize
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** Maps view_violations_full columns + payment join */
@Parcelize
@Serializable
data class Violation(
    val id: Int = 0,

    @SerialName("license_plate")
    val licensePlate: String? = null,

    @SerialName("license_plate_normalized")
    val licensePlateNormalized: String? = null,

    val confidence: Double? = null,

    @SerialName("full_image_url")
    val fullImageUrl: String? = null,

    @SerialName("cropped_vehicle_url")
    val croppedVehicleUrl: String? = null,

    @SerialName("cropped_plate_url")
    val croppedPlateUrl: String? = null,

    @SerialName("stop_line_snapshot_url")
    val stopLineSnapshotUrl: String? = null,

    @SerialName("violation_type")
    val violationType: String? = null,

    @SerialName("traffic_light_state")
    val trafficLightState: String? = null,

    val timestamp: String? = null,

    @SerialName("timestamp_vn")
    val timestampVn: String? = null,

    @SerialName("vote_count")
    val voteCount: Int? = null,

    @SerialName("vote_percent")
    val votePercent: Double? = null,

    @SerialName("track_id")
    val trackId: Int? = null,

    @SerialName("image_quality_score")
    val imageQualityScore: Double? = null,

    @SerialName("processing_time_ms")
    val processingTimeMs: Int? = null,

    // Payment fields
    @SerialName("fine_amount")
    val fineAmount: Int? = null,

    @SerialName("payment_status")
    val paymentStatus: String? = null,  // unpaid | pending | paid | failed

    @SerialName("paid_at")
    val paidAt: String? = null,

    @SerialName("payment_ref")
    val paymentRef: String? = null,

    // Camera / location
    @SerialName("camera_id")
    val cameraId: Int? = null,

    @SerialName("camera_name")
    val cameraName: String? = null,

    val location: String? = null,
    val latitude: Double? = null,
    val longitude: Double? = null,

    @SerialName("ip_address")
    val ipAddress: String? = null,

    // Payment join (lateral)
    @SerialName("payment_id")
    val paymentId: String? = null,

    @SerialName("payment_code")
    val paymentCode: String? = null,

    @SerialName("transfer_content")
    val transferContent: String? = null,

    @SerialName("payment_amount")
    val paymentAmount: Int? = null,

    @SerialName("payment_status_detail")
    val paymentStatusDetail: String? = null,

    @SerialName("vietqr_image_url")
    val vietqrImageUrl: String? = null,

    @SerialName("bank_account")
    val bankAccount: String? = null,

    @SerialName("bank_name")
    val bankName: String? = null,

    @SerialName("bank_bin")
    val bankBin: String? = null,

    @SerialName("payment_confirmed_at")
    val paymentConfirmedAt: String? = null,

    @SerialName("payment_expired_at")
    val paymentExpiredAt: String? = null,
) : Parcelable {

    /** Display label cho loại vi phạm */
    val violationLabel: String get() = when (violationType) {
        "red_light"  -> "Vượt đèn đỏ"
        "wrong_lane" -> "Sai làn đường"
        "speeding"   -> "Quá tốc độ"
        else         -> violationType ?: "--"
    }

    /** Display cho trạng thái đèn */
    val trafficLightLabel: String get() = when (trafficLightState) {
        "red"    -> "Đỏ"
        "yellow" -> "Vàng"
        "green"  -> "Xanh"
        else     -> trafficLightState ?: "--"
    }

    /** Số tiền hiển thị */
    val fineDisplay: String get() {
        val amount = fineAmount ?: 0
        return if (amount == 0) "Chưa xác định"
        else "%,d VNĐ".format(amount).replace(',', '.')
    }

    /** Trạng thái thanh toán hiển thị */
    val paymentStatusLabel: String get() = when (paymentStatus) {
        "unpaid"  -> "Chưa nộp phạt"
        "pending" -> "Đang chờ xác nhận"
        "paid"    -> "Đã thanh toán"
        "failed"  -> "Thanh toán thất bại"
        else      -> "Chưa nộp phạt"
    }

    val isPaid: Boolean get() = paymentStatus == "paid"
}

@Serializable
data class ViolationPayment(
    val id: String? = null,

    @SerialName("violation_id")
    val violationId: Int = 0,

    @SerialName("license_plate")
    val licensePlate: String = "",

    val amount: Int = 0,
    val status: String = "created",

    @SerialName("payment_code")
    val paymentCode: String = "",

    @SerialName("transfer_content")
    val transferContent: String? = null,

    @SerialName("vietqr_payload")
    val vietqrPayload: String? = null,

    @SerialName("vietqr_image_url")
    val vietqrImageUrl: String? = null,

    @SerialName("bank_account")
    val bankAccount: String? = null,

    @SerialName("bank_name")
    val bankName: String? = null,

    @SerialName("bank_bin")
    val bankBin: String? = null,

    @SerialName("sepay_transaction_id")
    val sepayTransactionId: String? = null,

    @SerialName("sepay_reference_code")
    val sepayReferenceCode: String? = null,

    @SerialName("created_at")
    val createdAt: String? = null,

    @SerialName("confirmed_at")
    val confirmedAt: String? = null,

    @SerialName("expired_at")
    val expiredAt: String? = null,
) {
    /** Build VietQR URL cho QR Image */
    fun buildVietQRUrl(): String {
        val bin    = bankBin ?: "970422"
        val acct   = bankAccount ?: "0332282868"
        val amt    = amount
        val addInfo = transferContent ?: "NOPPHAT $paymentCode"
        val name   = "NOPPHAT"
        return "https://img.vietqr.io/image/$bin-$acct-compact2.png?amount=$amt&addInfo=${addInfo.replace(" ", "%20")}&accountName=$name"
    }
}
