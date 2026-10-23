<?php
declare(strict_types=1);
namespace Annam;
/** Sole boundary that transmits queued WhatsApp messages. */
final class Sender {
    public function __construct(private Store $store) {}
    public function send(array $message,array $secrets): string {
        $payload=is_string($message['payload'])?json_decode($message['payload'],true,64,JSON_THROW_ON_ERROR):$message['payload'];$graph=MessagePayload::graph($message['to_phone'],$payload);
        if($secrets['wa_provider']==='console'){if(!in_array(getenv('APP_ENV'),['local','preview'],true))throw new HttpError(422,'Choose a live message provider before dispatching.');return 'local.'.$message['id'];}
        if($payload['kind']!=='template'){$conversation=$this->store->db->one('SELECT last_inbound_at FROM messaging_whatsappconversation WHERE tenant_id=? AND phone=?',[$this->store->id(),$message['to_phone']]);if(!$conversation||!$conversation['last_inbound_at']||strtotime($conversation['last_inbound_at'])<=time()-86400)throw new HttpError(422,'The 24-hour customer reply window is closed; use an approved template.');}
        if($secrets['wa_provider']==='meta_cloud'){
            if(!ctype_digit($secrets['wa_phone_number_id']))throw new HttpError(422,'Configure the Meta phone number ID.');$token=Crypto::decrypt($secrets['wa_token_enc']);if(!$token)throw new HttpError(422,'Configure the Meta access token.');
            $response=Http::json('POST','https://graph.facebook.com/v23.0/'.$secrets['wa_phone_number_id'].'/messages',['Authorization'=>'Bearer '.$token],$graph);$id=$response['messages'][0]['id']??'';if(!is_string($id)||!$id||strlen($id)>120)throw new ProviderError(true);return $id;
        }
        if($secrets['wa_provider']!=='n8n'||!$secrets['n8n_send_url'])throw new HttpError(422,'Configure a WhatsApp sender.');$token=Crypto::decrypt($secrets['n8n_auth_token_enc']);
        $result=Http::json('POST',$secrets['n8n_send_url'],$token?['Authorization'=>'Bearer '.$token]:[],['tenant'=>$this->store->tenant['slug'],'to'=>$message['to_phone'],'purpose'=>$message['purpose'],'message_id'=>(int)$message['id'],'payload'=>$payload,'graph'=>$graph],true);$id=(string)($result['message_id']??$result['wamid']??'');if(strlen($id)>120)throw new ProviderError(true);return $id;
    }
    public function forward(array $event,array $secrets): void {
        if(!$secrets['n8n_receive_url'])throw new HttpError(422,'No n8n forwarding URL is configured.');$token=Crypto::decrypt($secrets['n8n_auth_token_enc']);Http::json('POST',$secrets['n8n_receive_url'],$token?['Authorization'=>'Bearer '.$token]:[],json_decode($event['payload'],true,64,JSON_THROW_ON_ERROR),true);
    }
}
