package com.codex.tgbotcontrol;
public class AbstergoApplication extends android.app.Application {
    @Override public void onConfigurationChanged(android.content.res.Configuration config){
        super.onConfigurationChanged(config);
        for(int id:PowerWidget.ids(this))PowerWidget.render(this,id);
    }
    @Override public void onCreate(){
        super.onCreate();
        for(int id:PowerWidget.ids(this))PowerWidget.render(this,id);
    }
}
