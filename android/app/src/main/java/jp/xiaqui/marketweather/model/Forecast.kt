package jp.xiaqui.marketweather.model
import com.google.gson.annotations.SerializedName
data class Forecast(
    @SerializedName("generated_at") val generatedAt: String,
    val markets: List<Market>,
)
