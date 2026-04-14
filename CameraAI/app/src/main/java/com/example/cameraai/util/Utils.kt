package com.example.cameraai.util

import android.content.Context
import android.content.SharedPreferences
import androidx.core.content.edit

/** Lưu trữ local: biển số đã tra cứu, session */
object Prefs {
    private const val PREF_NAME   = "violation_lookup"
    private const val KEY_PLATE   = "saved_plate"
    private const val KEY_NORM    = "saved_plate_normalized"
    private const val KEY_DEVICE  = "device_id"

    private fun sp(ctx: Context): SharedPreferences =
        ctx.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE)

    fun savePlate(ctx: Context, plate: String, normalized: String) {
        sp(ctx).edit {
            putString(KEY_PLATE, plate)
            putString(KEY_NORM, normalized)
        }
    }

    fun getSavedPlate(ctx: Context) = sp(ctx).getString(KEY_PLATE, null)
    fun getSavedNorm(ctx: Context)  = sp(ctx).getString(KEY_NORM, null)

    fun clearPlate(ctx: Context) = sp(ctx).edit { remove(KEY_PLATE); remove(KEY_NORM) }

    fun getDeviceId(ctx: Context): String {
        var id = sp(ctx).getString(KEY_DEVICE, null)
        if (id == null) {
            id = java.util.UUID.randomUUID().toString()
            sp(ctx).edit { putString(KEY_DEVICE, id) }
        }
        return id
    }
}

/** Normalize biển số xe Việt Nam */
object PlateUtils {
    /** Bỏ khoảng trắng, dấu chấm, gạch; uppercase */
    fun normalize(plate: String): String =
        plate.trim().replace(Regex("[^A-Za-z0-9]"), "").uppercase()

    /** Validate cơ bản — biển số VN: 8-10 ký tự alphanumeric */
    fun isValid(plate: String): Boolean {
        val n = normalize(plate)
        return n.length in 8..11
    }
}
