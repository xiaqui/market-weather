package jp.xiaqui.marketweather.model
import com.google.gson.annotations.SerializedName
data class Market(
    val id: String,
    val name: String,
    val current: Double,
    @SerializedName("up_probability") val upProbability: Double,
    @SerializedName("range_low") val rangeLow: Double,
    @SerializedName("range_high") val rangeHigh: Double,
    val confidence: Double,
    val weather: String,
    val risk: String,
)
