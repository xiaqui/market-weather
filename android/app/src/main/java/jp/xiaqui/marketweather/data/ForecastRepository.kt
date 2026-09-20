package jp.xiaqui.marketweather.data
import android.content.Context
import com.google.gson.Gson
import jp.xiaqui.marketweather.model.Forecast
import java.io.Reader
class ForecastRepository(private val gson: Gson = Gson()) {
    fun load(context: Context): Forecast =
        context.assets.open("forecast.json").bufferedReader().use(::parse)
    fun parse(reader: Reader): Forecast = gson.fromJson(reader, Forecast::class.java)
}
