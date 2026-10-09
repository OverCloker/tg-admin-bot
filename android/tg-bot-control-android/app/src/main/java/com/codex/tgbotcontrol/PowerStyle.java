package com.codex.tgbotcontrol;
import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.view.View;
import android.widget.*;
/** Shared native surfaces and typography for the power screen. */
final class PowerStyle {
    static final int PAGE=0xfffffcf7, INK=0xff1b2232, MUTED=0xff69727d,
        GREEN=0xff176b43, ON=0xffedf5ee, RED=0xffaf4334, OFF=0xfffceee9, NEUTRAL=0xfff0efed;
    static int dp(Context c,int n){return Math.round(n*c.getResources().getDisplayMetrics().density);}
    static GradientDrawable shape(Context c,int color,int radius){
        GradientDrawable d=new GradientDrawable();d.setColor(color);d.setCornerRadius(dp(c,radius));return d;
    }
    static void clickable(Context c,View v,int color,int radius){
        v.setBackground(new RippleDrawable(ColorStateList.valueOf(0x24176b43),shape(c,color,radius),shape(c,0xffffffff,radius)));
    }
    static TextView label(Context c,String value,int size,int color,boolean bold){
        TextView t=new TextView(c);t.setText(value);t.setTextSize(size);t.setTextColor(color);
        t.setFontFeatureSettings("tnum");t.setTypeface(Typeface.create(bold?"sans-serif-medium":"sans-serif",Typeface.NORMAL));
        t.setIncludeFontPadding(false);return t;
    }
    static Button button(Context c,String value,boolean primary){
        Button b=new Button(c);b.setText(value);b.setTextSize(15);b.setAllCaps(false);
        b.setTypeface(Typeface.create("sans-serif-medium",Typeface.NORMAL));b.setTextColor(primary?0xffffffff:GREEN);
        b.setMinHeight(dp(c,48));b.setMinimumHeight(dp(c,48));b.setPadding(dp(c,14),dp(c,10),dp(c,14),dp(c,10));
        b.setStateListAnimator(null);clickable(c,b,primary?GREEN:ON,14);return b;
    }
    static ImageView icon(Context c,int resource,int tint){
        ImageView i=new ImageView(c);i.setImageResource(resource);i.setImageTintList(ColorStateList.valueOf(tint));
        i.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_NO);return i;
    }
    private PowerStyle(){}
}
