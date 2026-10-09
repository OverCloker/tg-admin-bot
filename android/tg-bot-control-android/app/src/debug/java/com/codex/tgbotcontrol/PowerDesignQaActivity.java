package com.codex.tgbotcontrol;
import android.os.Bundle;
import org.json.*;
/** Deterministic, isolated page capture; never writes real widget preferences. */
public class PowerDesignQaActivity extends PowerActivity {
    @Override protected boolean isDesignPreview(){return true;}
    @Override protected int dataId(){return 99999;}
    @Override protected java.time.ZonedDateTime screenNow(){return java.time.ZonedDateTime.now(PowerData.KYIV).withHour(12).withMinute(31);}
    @Override public void onCreate(Bundle b){
        JSONObject data=new JSONObject();boolean empty=getIntent().getBooleanExtra("empty",false);
        try{
            data.put("date",screenNow().toLocalDate().toString()).put("published",!empty).put("group","2.2").put("location","/test").put("sourceUpdated","09.10.2026 12:31");
            JSONArray slots=new JSONArray();int[] pts={0,360,600,870,1080,1440};
            for(int i=0;i<5;i++)slots.put(new JSONObject().put("start",pts[i]).put("end",pts[i+1]).put("status",i%2==0?"on":"off"));
            data.put("intervals",slots);
        }catch(Exception e){throw new RuntimeException(e);}
        PowerData.prefs(this,dataId()).edit().putString("name","Київ").putString("path","/test").putString("group","2.2").putString("today",data.toString()).putString("widget_theme","light").putString("widget_transparency","0").apply();
        super.onCreate(b);display(data,false,false);
        getWindow().getDecorView().post(()->{
            try{
                android.view.ViewGroup root=findViewById(android.R.id.content);
                android.widget.ScrollView scroll=(android.widget.ScrollView)root.getChildAt(0);
                android.view.View content=scroll.getChildAt(0);
                android.graphics.Bitmap image=android.graphics.Bitmap.createBitmap(content.getWidth(),content.getHeight(),android.graphics.Bitmap.Config.ARGB_8888);
                android.graphics.Canvas canvas=new android.graphics.Canvas(image);canvas.drawColor(PowerStyle.PAGE);content.draw(canvas);
                try(java.io.FileOutputStream out=new java.io.FileOutputStream(new java.io.File(getExternalFilesDir(null),"power-page"+(empty?"-empty":"")+".png"))){image.compress(android.graphics.Bitmap.CompressFormat.PNG,100,out);}
            }catch(Exception e){android.util.Log.e("PowerQA","Capture failed",e);}
        });
    }
}
