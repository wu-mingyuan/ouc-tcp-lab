package com.ouc.tcp.test;

import com.ouc.tcp.client.Client;
import com.ouc.tcp.client.UDT_Timer;
import com.ouc.tcp.message.TCP_PACKET;

import java.util.*;
import java.util.logging.FileHandler;
import java.util.logging.Level;
import java.util.logging.Logger;
import java.util.logging.SimpleFormatter;

import java.util.logging.FileHandler;
import java.util.logging.Level;
import java.util.logging.Logger;
import java.util.logging.SimpleFormatter;


public class SenderSlidingWindow {
    private Client client;
    public int cwnd = 1;//拥塞窗口大小，初始值为1
    private volatile int ssthresh = 16;// 慢启动阈值，初始值为16
    private int count = 0;  // 拥塞避免： cwmd = cwmd + 1 / cwnd，每一个对新包的 ACK count++，所以 count == cwmd 时，cwnd = cwnd + 1
    private Hashtable<Integer, TCP_PACKET> packets = new Hashtable<Integer, TCP_PACKET>();
    private UDT_Timer timer; // 定时器，用于超时重传
    private int lastACKSequence = -1;
    private int lastACKSequenceCount = 0;

    // 创建日志记录器
    private static final Logger logger = Logger.getLogger(SenderSlidingWindow.class.getName());

    public SenderSlidingWindow(Client client) {
        this.client = client;

        // 配置日志记录器
        try {
            FileHandler fileHandler = new FileHandler("TCP_Sender.log", true); // true表示追加模式
            fileHandler.setFormatter(new SimpleFormatter());
            logger.addHandler(fileHandler);
            logger.setLevel(Level.INFO);
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
    // 判断是否已满
    public boolean isFull() {
        return this.cwnd <= this.packets.size();
    }
    //将数据包放入滑动窗口
    public void putPacket(TCP_PACKET packet) {
        int currentSequence = (packet.getTcpH().getTh_seq() - 1) / 100;
        this.packets.put(currentSequence, packet);
        
        //超时重传，3秒
        if (this.timer == null) {
            this.timer = new UDT_Timer();
            this.timer.schedule(new RetransmitTask(this), 3000, 3000);
        }
    }


    public void receiveACK(int currentSequence) {
        if (currentSequence == this.lastACKSequence) {
            this.lastACKSequenceCount++;//如果收到相同的ACK数据包，则count++
            if (this.lastACKSequenceCount == 4) {
                TCP_PACKET packet = this.packets.get(currentSequence + 1);//如果连续收到四个，则快速重传
                if (packet != null) {
                    this.client.send(packet);//重传

                    //充值定时器
                    if (this.timer != null) {
                        this.timer.cancel();
                    }
                    this.timer = new UDT_Timer();
                    this.timer.schedule(new RetransmitTask(this), 3000, 300);
                }

                fastRecovery();//快恢复
            }
        } else {
            //删掉已经确认的包
            List sequenceList = new ArrayList(this.packets.keySet());
            Collections.sort(sequenceList);
            for (int i = 0; i < sequenceList.size() && (Integer) sequenceList.get(i) <= currentSequence; i++) {
                this.packets.remove(sequenceList.get(i));
            }

            if (this.timer != null) {
                this.timer.cancel();
            }

            //如果有包未确认，则开启定时器
            if (this.packets.size() != 0) {
                this.timer = new UDT_Timer();
                this.timer.schedule(new RetransmitTask(this), 3000, 300);
            }

            this.lastACKSequence = currentSequence;
            this.lastACKSequenceCount = 1;

            //慢启动，指数增大
            if (this.cwnd < this.ssthresh) {
                this.cwnd++;
                System.out.println("########### window expand ############");
            } else {
                //拥塞避免,线性增大
                this.count++;
                if (this.count >= this.cwnd) {
                    this.count -= this.cwnd;
                    this.cwnd++;
                    System.out.println("########### window expand ############");
                }
            }
        }
    }

    //慢启动
    public void slowStart() {
        logger.info("Slow Start - Before: cwnd=" + this.cwnd + ", ssthresh=" + this.ssthresh);
        System.out.println("00000 cwnd: " + this.cwnd);
        System.out.println("00000 ssthresh: " + this.ssthresh);

        this.ssthresh = this.cwnd / 2;
        if (this.ssthresh < 2) {
            this.ssthresh = 2;
        }
        this.cwnd = 1;
        logger.info("Slow Start - After: cwnd=" + this.cwnd + ", ssthresh=" + this.ssthresh);
        System.out.println("11111 cwnd: " + this.cwnd);
        System.out.println("11111 ssthresh: " + this.ssthresh);
    }

    //快恢复
    public void fastRecovery() {
        logger.info("Fast Recovery - Before: cwnd=" + this.cwnd + ", ssthresh=" + this.ssthresh);
        System.out.println("Fast Recovery");
        System.out.println("00000 cwnd: " + this.cwnd);
        System.out.println("00000 ssthresh: " + this.ssthresh);
        this.ssthresh = this.cwnd / 2;
        if (this.ssthresh < 2) {
            this.ssthresh = 2;
        }
        this.cwnd = this.ssthresh;
        logger.info("Fast Recovery - After: cwnd=" + this.cwnd + ", ssthresh=" + this.ssthresh);
        System.out.println("11111 cwnd: " + this.cwnd);
        System.out.println("11111 ssthresh: " + this.ssthresh);
    }

    //重传
    public void retransmit() {
        this.timer.cancel();

        List sequenceList = new ArrayList(this.packets.keySet());
        Collections.sort(sequenceList);

        for (int i = 0; i < this.cwnd && i < sequenceList.size(); i++) {
            TCP_PACKET packet = this.packets.get(sequenceList.get(i));
            if (packet != null) {
                logger.info("Fast Recovery - After: cwnd=" + this.cwnd + ", ssthresh=" + this.ssthresh);
                System.out.println("retransmit: " + (packet.getTcpH().getTh_seq() - 1) / 100);
                this.client.send(packet);
            }
        }
        //如果还有未确认的数据包，重新启动定时器
        if (this.packets.size() != 0) {
            this.timer = new UDT_Timer();
            this.timer.schedule(new RetransmitTask(this), 3000, 3000);
        } else {
            System.out.println("000000000000000000 no packet");
            logger.info("No packets to retransmit");
        }
    }
}



class RetransmitTask extends TimerTask {
    private SenderSlidingWindow window;

    public RetransmitTask(SenderSlidingWindow window) {
        this.window = window;
    }

    @Override
    public void run() {
        System.out.println("--- Time Out ---");
        this.window.slowStart();

        this.window.retransmit();
    }
}
