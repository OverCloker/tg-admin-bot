package com.codex.tgbotcontrol;
import android.app.Activity;
import android.os.Bundle;
import android.widget.*;
import android.view.*;
import android.graphics.*;
import org.json.*;
import java.time.*;

/** Local emulator-only rendering harness; does not modify chat or widget caches. */
public class WidgetDesignQaActivity extends Activity {
    @Override public void onCreate(Bundle b) {
        super.onCreate(b);
        int w=getIntent().getIntExtra("width",180),h=getIntent().getIntExtra("height",420);
        boolean all=getIntent().getBooleanExtra("allDay",false),empty=getIntent().getBooleanExtra("empty",false);
        ZonedDateTime now=ZonedDateTime.now(PowerData.KYIV).withHour(14).withMinute(45);
        android.content.SharedPreferences prefs=getSharedPreferences("widget_qa",0);
        String theme=getIntent().getStringExtra("theme");if(theme==null)theme="light";
        int transparency=getIntent().getIntExtra("transparency",0);
        prefs.edit().putString("name","Чутове").putString("group","2.2").putString("path","/test").putString("widget_theme",theme).putString("widget_transparency",Integer.toString(transparency)).apply();
        JSONObject d=new JSONObject();
        try {
            d.put("date",now.toLocalDate().toString()).put("published",!empty).put("group","2.2").put("location","/test").put("sourceUpdated","09.10.2026 14:45").put("fetchedAt",now.toString());
            JSONArray intervals=new JSONArray();
            int[] points=all?new int[]{0,1440}:new int[]{0,360,570,870,1080,1440};
            for(int i=0;i<points.length-1;i++)intervals.put(new JSONObject().put("start",points[i]).put("end",points[i+1]).put("status",i%2==0?"on":"off"));
            d.put("intervals",intervals);
        }catch(Exception e){throw new RuntimeException(e);}
        boolean preview=getIntent().getBooleanExtra("preview",false);
        boolean fallback=getIntent().getBooleanExtra("fallback",false),hosted=getIntent().getBooleanExtra("hosted",false);
        Bundle options=new Bundle();
        options.putInt(android.appwidget.AppWidgetManager.OPTION_APPWIDGET_MIN_WIDTH,w);options.putInt(android.appwidget.AppWidgetManager.OPTION_APPWIDGET_MAX_WIDTH,w);
        options.putInt(android.appwidget.AppWidgetManager.OPTION_APPWIDGET_MIN_HEIGHT,h);options.putInt(android.appwidget.AppWidgetManager.OPTION_APPWIDGET_MAX_HEIGHT,h);
        android.widget.RemoteViews remote=preview?AdaptivePowerViews.preview(this):fallback?AdaptivePowerViews.fallback(this,0,prefs,d,new JSONObject(),now,options):AdaptivePowerViews.make(this,0,prefs,d,new JSONObject(),now,w,h);
        View content;
        if(hosted){
            android.appwidget.AppWidgetHostView host=new android.appwidget.AppWidgetHostView(this);
            android.appwidget.AppWidgetProviderInfo info=null;
            for(android.appwidget.AppWidgetProviderInfo p:android.appwidget.AppWidgetManager.getInstance(this).getInstalledProviders())if(p.provider.getClassName().equals(PowerWidget.class.getName()))info=p;
            if(info==null)throw new IllegalStateException("Provider not installed");
            host.setAppWidget(999999,info);host.setPadding(0,0,0,0);host.updateAppWidget(remote);content=host;
        }else content=remote.apply(this,null);
        int pxw=Math.round(w*getResources().getDisplayMetrics().density),pxh=Math.round(h*getResources().getDisplayMetrics().density);
        LinearLayout stage=new LinearLayout(this);stage.setGravity(Gravity.CENTER);stage.setBackgroundColor(0xffe8e3da);
        stage.addView(content,new LinearLayout.LayoutParams(pxw,pxh));setContentView(stage);
        content.post(()->{
            try{
                Bitmap image=Bitmap.createBitmap(content.getWidth(),content.getHeight(),Bitmap.Config.ARGB_8888);
                content.draw(new Canvas(image));
                String suffix=preview?"-preview":all?"-all":empty?"-empty":"";
                if(fallback)suffix+="-fallback";if(hosted)suffix+="-host";
                if(!"light".equals(prefs.getString("widget_theme","light"))||transparency!=0)suffix+="-"+prefs.getString("widget_theme","light")+"-"+transparency;
                try(java.io.FileOutputStream out=new java.io.FileOutputStream(new java.io.File(getExternalFilesDir(null),"widget-"+w+"x"+h+suffix+".png"))){image.compress(Bitmap.CompressFormat.PNG,100,out);}
            }catch(Exception e){android.util.Log.e("WidgetQA","Snapshot failed",e);}
        });
    }
}
