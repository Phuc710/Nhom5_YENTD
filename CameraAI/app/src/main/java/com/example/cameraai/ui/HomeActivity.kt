package com.example.cameraai.ui

import android.app.DatePickerDialog
import android.content.Intent
import android.os.Bundle
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.example.cameraai.R
import com.example.cameraai.data.SupabaseClient
import com.example.cameraai.data.model.Violation
import com.example.cameraai.databinding.ActivityHomeBinding
import com.example.cameraai.ui.adapter.ViolationAdapter
import com.example.cameraai.util.Prefs
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.*

class HomeActivity : AppCompatActivity() {

    companion object {
        const val EXTRA_PLATE      = "extra_plate"
        const val EXTRA_PLATE_NORM = "extra_plate_norm"
    }

    private lateinit var binding: ActivityHomeBinding
    private lateinit var adapter: ViolationAdapter

    private var plate     = ""
    private var plateNorm = ""
    private var allList   = listOf<Violation>()
    private var fromDate: String? = null
    private var toDate:   String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityHomeBinding.inflate(layoutInflater)
        setContentView(binding.root)

        plate     = intent.getStringExtra(EXTRA_PLATE)     ?: Prefs.getSavedPlate(this) ?: ""
        plateNorm = intent.getStringExtra(EXTRA_PLATE_NORM) ?: Prefs.getSavedNorm(this)  ?: ""

        setupToolbar()
        setupRecycler()
        setupFilters()
        loadViolations()
    }

    private fun setupToolbar() {
        setSupportActionBar(binding.toolbar)
        supportActionBar?.title = "Biển số: $plate"
        supportActionBar?.subtitle = "Lịch sử vi phạm"
    }

    private fun setupRecycler() {
        adapter = ViolationAdapter { viol ->
            val intent = Intent(this, DetailActivity::class.java).apply {
                putExtra(DetailActivity.EXTRA_VIOLATION, viol)
            }
            startActivity(intent)
        }
        binding.rvViolations.layoutManager = LinearLayoutManager(this)
        binding.rvViolations.adapter = adapter
    }

    private fun setupFilters() {
        // Search
        binding.btnSearch.setOnClickListener { applyFilter() }
        binding.etSearch.setOnEditorActionListener { _, _, _ -> applyFilter(); true }

        // Date from / to
        binding.btnFromDate.setOnClickListener { pickDate(isFrom = true) }
        binding.btnToDate.setOnClickListener   { pickDate(isFrom = false) }
        binding.btnClearDate.setOnClickListener {
            fromDate = null; toDate = null
            binding.btnFromDate.text = "Từ ngày"
            binding.btnToDate.text   = "Đến ngày"
            applyFilter()
        }

        // Sort
        binding.chipNewest.setOnClickListener { sortList(descending = true) }
        binding.chipOldest.setOnClickListener { sortList(descending = false) }

        // Pull-to-refresh
        binding.swipeRefresh.setOnRefreshListener { loadViolations() }
    }

    private fun loadViolations() {
        binding.swipeRefresh.isRefreshing = true
        binding.progressBar.visibility = View.VISIBLE
        lifecycleScope.launch {
            try {
                allList = SupabaseClient.getViolationsByPlate(
                    normalizedPlate = plateNorm,
                    fromDate = fromDate,
                    toDate   = toDate,
                )
                applyFilter()
                updateStats()
            } catch (e: Exception) {
                Toast.makeText(this@HomeActivity, "Lỗi tải dữ liệu: ${e.message}", Toast.LENGTH_LONG).show()
            } finally {
                binding.swipeRefresh.isRefreshing = false
                binding.progressBar.visibility = View.GONE
            }
        }
    }

    private fun applyFilter() {
        val query = binding.etSearch.text.toString().trim()
        val filtered = allList.filter { v ->
            query.isEmpty() ||
            v.licensePlate?.contains(query, ignoreCase = true) == true ||
            v.violationLabel.contains(query, ignoreCase = true) ||
            v.cameraName?.contains(query, ignoreCase = true) == true ||
            v.location?.contains(query, ignoreCase = true) == true
        }
        sortList(descending = true, list = filtered)

        if (filtered.isEmpty()) {
            binding.tvEmpty.visibility = View.VISIBLE
            binding.rvViolations.visibility = View.GONE
        } else {
            binding.tvEmpty.visibility = View.GONE
            binding.rvViolations.visibility = View.VISIBLE
        }
    }

    private fun sortList(descending: Boolean, list: List<Violation> = allList) {
        val sorted = if (descending)
            list.sortedByDescending { it.timestamp }
        else
            list.sortedBy { it.timestamp }
        adapter.submitList(sorted)
    }

    private fun updateStats() {
        val unpaid = allList.count { it.paymentStatus != "paid" }
        binding.tvStats.text = "Tổng: ${allList.size} vi phạm · Chưa nộp: $unpaid"
    }

    private fun pickDate(isFrom: Boolean) {
        val cal = Calendar.getInstance()
        DatePickerDialog(this, { _, y, m, d ->
            val sdf = SimpleDateFormat("yyyy-MM-dd", Locale.getDefault())
            val cal2 = Calendar.getInstance().also { it.set(y, m, d) }
            val dateStr = sdf.format(cal2.time) + (if (isFrom) "T00:00:00Z" else "T23:59:59Z")
            val label = "%02d/%02d/%04d".format(d, m + 1, y)
            if (isFrom) { fromDate = dateStr; binding.btnFromDate.text = label }
            else        { toDate   = dateStr; binding.btnToDate.text   = label }
            loadViolations()
        }, cal.get(Calendar.YEAR), cal.get(Calendar.MONTH), cal.get(Calendar.DAY_OF_MONTH)).show()
    }

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menuInflater.inflate(R.menu.menu_home, menu)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        if (item.itemId == R.id.action_logout) {
            Prefs.clearPlate(this)
            startActivity(Intent(this, LoginActivity::class.java))
            finish()
        }
        return super.onOptionsItemSelected(item)
    }

    override fun onResume() {
        super.onResume()
        // Reload để cập nhật payment_status sau khi quay lại từ PaymentActivity
        loadViolations()
    }
}
